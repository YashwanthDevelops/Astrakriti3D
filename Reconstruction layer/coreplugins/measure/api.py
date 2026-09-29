import os
from django.core import signing
from rest_framework import exceptions
from rest_framework import serializers
from rest_framework import status
from rest_framework.response import Response
from app.api.workers import CheckTask, GetTaskResult
from app.plugins.views import TaskView
from django.utils.translation import gettext_lazy as _
from app.plugins.worker import run_function_async

from .volume import calc_volume

VOLUME_JOB_TOKEN_SALT = "webodm.measure.volume-job"
VOLUME_JOB_TOKEN_MAX_AGE = 60 * 60


def _volume_job_token(task_id, celery_task_id):
    return signing.dumps(
        {"task_id": str(task_id), "celery_task_id": str(celery_task_id)},
        salt=VOLUME_JOB_TOKEN_SALT,
    )


def _check_volume_job_token(request, task, celery_task_id):
    token = request.META.get("HTTP_X_VOLUME_JOB_TOKEN", "")
    try:
        payload = signing.loads(
            token,
            salt=VOLUME_JOB_TOKEN_SALT,
            max_age=VOLUME_JOB_TOKEN_MAX_AGE,
        )
    except signing.BadSignature:
        raise exceptions.NotFound()
    if payload != {"task_id": str(task.pk), "celery_task_id": str(celery_task_id)}:
        raise exceptions.NotFound()

class VolumeRequestSerializer(serializers.Serializer):
    area = serializers.JSONField(help_text="GeoJSON Polygon contour defining the volume area to compute")
    method = serializers.CharField(help_text="One of: [plane,triangulate,average,custom,highest,lowest]", default="triangulate", allow_blank=True)

class TaskVolume(TaskView):
    def post(self, request, pk=None):
        task = self.get_and_check_task(request, pk)
        if task.dsm_extent is None:
            return Response({'error': _('No surface model available. From the Dashboard, select this task, press Edit, from the options make sure to check "dsm", then press Restart --> From DEM.')})

        serializer = VolumeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        area = serializer['area'].value
        method = serializer['method'].value
        points = [coord for coord in area['geometry']['coordinates'][0]]
        dsm = os.path.abspath(task.get_asset_download_path("dsm.tif"))

        try: 
            celery_task_id = run_function_async(calc_volume, input_dem=dsm, pts=points, pts_epsg=4326, base_method=method).task_id
            return Response({
                'celery_task_id': celery_task_id,
                'result_token': _volume_job_token(task.pk, celery_task_id),
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_200_OK)

class TaskVolumeResult(TaskView):
    def get(self, request, pk=None, celery_task_id=None):
        # Celery result IDs are not authorization. Reuse WebODM's normal
        # Task visibility check before polling or returning worker output.
        task = self.get_and_check_task(request, pk)
        _check_volume_job_token(request, task, celery_task_id)
        response = GetTaskResult.get(self, request, celery_task_id, task=task)
        if response.status_code == status.HTTP_200_OK and isinstance(response.data, dict) and 'output' in response.data:
            from worker.tasks import TestSafeAsyncResult
            result = TestSafeAsyncResult(celery_task_id).get()
            if isinstance(result, dict):
                response.data['unit_context'] = result.get('unit_context')
        return response

    def handle_output(self, output, result, **kwargs):
        return output


class TaskVolumeCheck(TaskView):
    def get(self, request, pk=None, celery_task_id=None):
        # Keep worker progress/error polling inside the Task visibility boundary.
        task = self.get_and_check_task(request, pk)
        _check_volume_job_token(request, task, celery_task_id)
        return CheckTask().get(request, celery_task_id)


