import './circles.scss';

import { LoadingAndErrorIndicator } from 'application/frontend/src/components/LoadingAndErrorIndicator';
import useWindowDimensions from 'application/frontend/src/hooks/useWindowDimensions';
import { useDataStore } from 'application/frontend/src/providers/DataProvider';
import * as d3 from 'd3';
import React, { useEffect, useState } from 'react';
import { Button, Icon } from 'semantic-ui-react';

export const ExplorerCircles = () => {
  const { height, width } = useWindowDimensions();
  const [useFullScreen, setUseFullScreen] = useState(false);
  const { dataLoading, dataTree } = useDataStore();

  useEffect(() => {
    var svg = d3.select('svg');
    svg.selectAll('*').remove();
    var margin = 20,
      diameter = +svg.attr('width'),
      g = svg.append('g').attr('transform', 'translate(' + diameter / 2 + ',' + diameter / 2 + ')');

    var color = d3
      .scaleLinear([-1, 5], ['hsl(152,80%,80%)', 'hsl(228,30%,40%)'])
      .interpolate(d3.interpolateHcl);

    var pack = d3
      .pack()
      .size([diameter - margin, diameter - margin])
      .padding(2);

    const populateChildren = (node) => {
      node.children = [];
      if (node.links) {
        node.children = node.links.filter((x) => x.document && x.ltype !== 'Related').map((x) => x.document);
      }
      node.children.forEach((x) => populateChildren(x));
      node.children.forEach((x) => {
        if (x.children.length === 0) x.size = 1;
      });
    };

    const dataTreeClone = structuredClone(dataTree);
    dataTreeClone.forEach((node) => populateChildren(node));

    let root: any = {
      displayName: 'cluster',
      children: dataTreeClone,
    };

    root = d3
      .hierarchy(root)
      .sum(function (d: any) {
        return d.size;
      })
      .sort(function (a: any, b: any) {
        return b.value - a.value;
      });

    var focus: any = root,
      nodes = pack(root).descendants(),
      view;

    var circle = g
      .selectAll('circle')
      .data(nodes)
      .enter()
      .append('circle')
      .attr('class', function (d) {
        return d.parent ? (d.children ? 'node' : 'node node--leaf') : 'node node--root';
      })
      .style('fill', function (d: any) {
        return d.children ? color(d.depth) : d.data.color ? d.data.color : null;
      })
      .on('click', function (event, d: any) {
        if (focus !== d) zoom(event, d), event.stopPropagation();
      });

    var text = g
      .selectAll('text')
      .data(nodes)
      .enter()
      .append('text')
      .attr('class', 'label')
      .style('fill-opacity', function (d: any) {
        return d.parent === root ? 1 : 0;
      })
      .style('display', function (d: any) {
        return d.parent === root ? 'inline' : 'none';
      })
      .text(function (d: any) {
        let name =
          d.data.displayName.length > 33 ? d.data.displayName.substr(0, 33) + '...' : d.data.displayName;
        if (d.data.children && d.data.children.length > 0) name += ' (' + d.data.children.length + ')';
        return name;
      });

    var node = g.selectAll('circle,text');

    svg.style('background', color(-1)).on('click', function (event) {
      zoom(event, root);
    });

    zoomTo([root.x, root.y, root.r * 2 + margin]);

    function zoom(event: any, d: any) {
      var focus0 = focus;
      focus = d;

      var transition = d3
        .transition()
        .duration(event.altKey ? 7500 : 750)
        .tween('zoom', function (d) {
          var i = d3.interpolateZoom(view, [focus.x, focus.y, focus.r * 2 + margin]);
          return function (t) {
            zoomTo(i(t));
          };
        });

      transition
        .selectAll('text')
        .filter(function (d: any) {
          const el = this as HTMLElement;
          return (d && d.parent === focus) || el.style.display === 'inline';
        })
        .style('fill-opacity', function (d: any) {
          return d && d.parent === focus ? 1 : 0;
        })
        .on('start', function (d: any) {
          const el = this as HTMLElement;
          if (d && d.parent === focus) el.style.display = 'inline';
        })
        .on('end', function (d: any) {
          const el = this as HTMLElement;
          if (d && d.parent !== focus) el.style.display = 'none';
        });
    }

    function zoomTo(v) {
      var k = diameter / v[2];
      view = v;
      node.attr('transform', function (d: any) {
        return 'translate(' + (d.x - v[0]) * k + ',' + (d.y - v[1]) * k + ')';
      });
      circle.attr('r', function (d) {
        return d.r * k;
      });
    }
  }, [useFullScreen]);
  const defaultSize = width > height ? height - 100 : width;
  const size = useFullScreen ? width : defaultSize;
  return (
    <div>
      <LoadingAndErrorIndicator loading={dataLoading} error={null} />
      <div style={{ display: 'block', margin: 'auto', width: 'fit-content' }}>
        <div style={{ position: 'relative' }}>
          <Button icon onClick={() => setUseFullScreen(!useFullScreen)} className="screen-size-button">
            <Icon name={useFullScreen ? 'compress' : 'expand'} />
          </Button>
        </div>
        <svg
          width={size}
          height={size}
          style={{ background: 'rgb(163, 245, 207)', display: 'block', margin: 'auto' }}
        >
          <g transform="translate(480,480)"></g>
        </svg>
      </div>
    </div>
  );
};
