import React from 'react';
import { mount } from 'enzyme';
import Map from '../Map';
import sinon from 'sinon';

sinon.useFakeXMLHttpRequest();

describe('<Map />', () => {
  it('renders without exploding', () => {
    const wrapper = mount(<Map 
    	tiles={[]} />);

    expect(wrapper.exists()).toBe(true);
  })

  it('names the map region and associates its opacity control', () => {
    const wrapper = mount(<Map
      tiles={[{meta: {task: {id: 7, name: 'Test reconstruction'}}}]}
      mapType="orthophoto" />);
    const region = wrapper.find('[role="region"]');
    const opacity = wrapper.find('#map-layer-opacity');
    const descriptionId = region.prop('aria-describedby');

    expect(region.prop('aria-label')).toContain('Test reconstruction');
    expect(wrapper.find(`#${descriptionId}`).text()).toContain('arrow keys');
    expect(wrapper.find('label').filterWhere(label => label.prop('htmlFor') === opacity.prop('id')).exists()).toBe(true);
  })
});
