def get_volume_unit_context(rasterio_ds):
    """Resolve volume conversion factors without silently treating unknown units as metres.

    ODM DSMs commonly omit the GeoTIFF band-unit tag. For a projected DSM only,
    use the CRS linear unit as an explicit *assumption* for Z and return that
    qualification for the UI to preserve. A declared but unsupported band unit,
    or a non-projected CRS, is not safe to convert and is rejected.
    """
    crs = rasterio_ds.crs
    if crs is None or not crs.is_projected:
        raise ValueError("DSM volume requires a projected CRS with known linear units")

    try:
        xy_unit_name, xy_to_m = crs.linear_units_factor
        xy_to_m = float(xy_to_m)
    except (AttributeError, TypeError, ValueError):
        raise ValueError("DSM volume could not determine projected CRS linear units")
    if not xy_unit_name or not (xy_to_m > 0):
        raise ValueError("DSM volume could not determine projected CRS linear units")

    band_units = rasterio_ds.units
    z_unit_name = band_units[0] if band_units else None
    if z_unit_name is not None and z_unit_name.strip():
        z_unit_name = z_unit_name.strip()
        z_unit_to_m = {
            "m": 1.0, "metre": 1.0, "meter": 1.0,
            "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
            "US survey foot": 1200.0 / 3937.0,
        }
        if z_unit_name not in z_unit_to_m:
            raise ValueError("DSM vertical unit is unsupported; volume cannot be reported in cubic metres")
        z_to_m = z_unit_to_m[z_unit_name]
        z_unit_source = "DSM band metadata"
    else:
        # ODM's generated DSMs may omit band unit tags. This is a disclosed
        # convention/assumption, not evidence of a known vertical datum.
        z_unit_name = xy_unit_name
        z_to_m = xy_to_m
        z_unit_source = "assumed from projected CRS; DSM band unit is absent"

    return {
        "units": "m³",
        "horizontal_unit": xy_unit_name,
        "vertical_unit": z_unit_name,
        "vertical_unit_source": z_unit_source,
        "vertical_datum": "unknown",
        "limitation": (
            "DSM vertical datum is unknown. "
            + ("Vertical unit is assumed to match the projected CRS because DSM band metadata is absent." if z_unit_source.startswith("assumed") else "")
        ).strip(),
        "xy_to_m": xy_to_m,
        "z_to_m": z_to_m,
    }


def calc_volume(input_dem, pts=None, pts_epsg=None, geojson_polygon=None, decimals=4,
                base_method="triangulate", custom_base_z=None):
    try:
        import os
        import rasterio
        import rasterio.mask
        from osgeo import osr
        from scipy.optimize import curve_fit
        from scipy.interpolate import griddata
        import numpy as np
        import json
        import warnings

        osr.UseExceptions()
        warnings.filterwarnings("ignore", module='scipy.optimize')

        if not os.path.isfile(input_dem):
            raise IOError(f"{input_dem} does not exist")

        crs = None
        unit_context = None

        with rasterio.open(input_dem) as d:
            if d.crs is None:
                raise ValueError(f"{input_dem} does not have a CRS")
            unit_context = get_volume_unit_context(d)
            crs = osr.SpatialReference()
            crs.ImportFromWkt(d.crs.to_wkt())
            crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

        if pts is None and pts_epsg is None and geojson_polygon is not None:
            # Read GeoJSON points
            pts = read_polygon(geojson_polygon)
            return calc_volume(input_dem, pts=pts, pts_epsg=4326, decimals=decimals, base_method=base_method, custom_base_z=custom_base_z)
        
        # Convert to DEM crs
        src_crs = osr.SpatialReference()
        src_crs.ImportFromEPSG(pts_epsg)
        transformer = osr.CoordinateTransformation(src_crs, crs)

        dem_pts = [list(transformer.TransformPoint(p[1], p[0]))[:2] for p in pts]
        
        # Some checks
        if len(dem_pts) < 2:
            raise ValueError("Insufficient points to form a polygon")

        # Close loop if needed
        if not np.array_equal(dem_pts[0], dem_pts[-1]):
            dem_pts.append(dem_pts[0])
        
        polygon = {"coordinates": [dem_pts], "type": "Polygon"}
        dem_pts = np.array(dem_pts)

        # Remove last point (loop close)
        dem_pts = dem_pts[:-1]
        
        with rasterio.open(input_dem) as d:
            px_w = d.transform[0]
            px_h = d.transform[4]

            # Area of a pixel in square units
            px_area = abs(px_w * px_h)

            rast_dem, transform = rasterio.mask.mask(d, [polygon], crop=True, all_touched=True, indexes=1, nodata=np.nan)
            h, w = rast_dem.shape

            # Do not silently turn an incomplete footprint into a plausible
            # zero/partial volume. The measurement acceptance contract needs a
            # truthful failure state when the selected polygon intersects
            # NoData or an incompletely covered DSM.
            if not np.isfinite(rast_dem).all():
                raise ValueError("Selected footprint intersects NoData or incomplete DSM coverage")

            # X/Y coordinates in transform coordinates
            ys, xs = np.array(rasterio.transform.rowcol(transform, dem_pts[:,0], dem_pts[:,1]))

            if np.any(xs<0) or np.any(xs>=w) or np.any(ys<0) or np.any(ys>=h):
                raise ValueError("Points are out of bounds")
            
            zs = rast_dem[ys,xs]

            if base_method == "plane":
                # Create a grid for interpolation
                x_grid, y_grid = np.meshgrid(np.linspace(0, w - 1, w), np.linspace(0, h - 1, h))

                # Perform curve fitting
                linear_func = lambda xy, m1, m2, b: m1 * xy[0] + m2 * xy[1] + b
                params, covariance = curve_fit(linear_func, np.vstack((xs, ys)), zs)

                base = linear_func((x_grid, y_grid), *params)
            elif base_method == "triangulate":
                # Create a grid for interpolation
                x_grid, y_grid = np.meshgrid(np.linspace(0, w - 1, w), np.linspace(0, h - 1, h))
                
                # Tessellate the input point set to N-D simplices, and interpolate linearly on each simplex. 
                base = griddata(np.column_stack((xs, ys)), zs, (x_grid, y_grid), method='linear')
            elif base_method == "average":
                base = np.full((h, w), np.mean(zs))
            elif base_method == "custom":
                if custom_base_z is None:
                    raise ValueError("Base method set to custom, but no custom base Z specified")
                base = np.full((h, w), float(custom_base_z))
            elif base_method == "highest":
                base = np.full((h, w), np.max(zs))
            elif base_method == "lowest":
                base = np.full((h, w), np.min(zs))
            else:
                raise ValueError(f"Invalid base method {base_method}")

            base[np.isnan(rast_dem)] = np.nan

            # Calculate volume
            diff = rast_dem - base
            volume = np.nansum(diff) * px_area
            volume *= unit_context["xy_to_m"] ** 2 * unit_context["z_to_m"]

            # import matplotlib.pyplot as plt
            # fig, ax = plt.subplots()
            # ax.imshow(base)
            # plt.scatter(xs, ys, c=zs, cmap='viridis', s=50, edgecolors='k')
            # plt.colorbar(label='Z values')
            # plt.title('Debug')
            # plt.show()

            return {
                'output': np.abs(np.round(volume, decimals=decimals)),
                'unit_context': {key: value for key, value in unit_context.items() if key not in ("xy_to_m", "z_to_m")},
            }
    except Exception as e:
        return {'error': str(e)}

def read_polygon(file):
    with open(file, 'r', encoding="utf-8") as f:
        data = json.load(f)

    if data.get('type') == "FeatureCollection":
        features = data.get("features", [{}])
    else:
        features = [data]

    for feature in features:
        if not 'geometry' in feature:
            continue

        # Check if the feature geometry type is Polygon
        if feature['geometry']['type'] == 'Polygon':
            # Extract polygon coordinates
            coordinates = feature['geometry']['coordinates'][0]  # Assuming exterior ring
            return coordinates
    
    raise IOError("No polygons found in %s" % file)
