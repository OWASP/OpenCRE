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
  const [breadcrumb, setBreadcrumb] = useState<string[]>([]);

  const rootRef = React.useRef<any>(null);
  const zoomRef = React.useRef<any>(null);
  const updateBreadcrumbRef = React.useRef<any>(null);
  const viewRef = React.useRef<any>(null);
  const zoomToRef = React.useRef<any>(null);
  const margin = 20;

  useEffect(() => {
    var svg = d3.select('svg');
    svg.selectAll('*').remove();

    var diameter = +svg.attr('width'),
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

    // Create tooltip div for hover labels
    const tooltip = d3
      .select('body')
      .append('div')
      .attr('class', 'circle-tooltip')
      .style('position', 'absolute')
      .style('visibility', 'hidden')
      .style('background-color', 'white')
      .style('padding', '5px')
      .style('border-radius', '3px')
      .style('border', '1px solid #ccc')
      .style('pointer-events', 'none')
      .style('z-index', '10');

    // Update breadcrumb when focus changes
    const updateBreadcrumb = (d: any) => {
      if (d === root) {
        setBreadcrumb(['Cluster']);
        return;
      }

      let path: string[] = [];
      let current = d;

      while (current && current !== root) {
        if (current.data.displayName && current.data.displayName !== 'cluster') {
          // Remove "CRE: " prefix if it exists
          const displayName = current.data.displayName.replace(/^CRE: /, '');
          path.unshift(displayName);
        }
        current = current.parent;
      }
      path.unshift('Cluster');
      setBreadcrumb(path);
    };

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
      //New mouseover to use id if diaplayName is not present (most likely for white dots )
      .on('mouseover', function (event, d: any) {
        // Prefer displayName, fallback to id
        const label = d.data.displayName
          ? d.data.displayName.replace(/^CRE: /, '')
          : d.data.id
          ? d.data.id
          : '';

        if (label) {
          tooltip
            .html(label)
            .style('visibility', 'visible')
            .style('top', event.pageY - 10 + 'px')
            .style('left', event.pageX + 10 + 'px');
        }
      })
      .on('mousemove', function (event) {
        tooltip.style('top', event.pageY - 10 + 'px').style('left', event.pageX + 10 + 'px');
      })
      .on('mouseout', function () {
        tooltip.style('visibility', 'hidden');
      })
      .on('click', function (event, d: any) {
        if (focus !== d) {
          updateBreadcrumb(d);
          zoom(event, d);
          event.stopPropagation();
        }
      });

    let showLabels = false; // Global toggle -->toggle this to true to show labels normally and during zoom

    var text = g
      .selectAll('text')
      .data(nodes)
      .enter()
      .append('text')
      .attr('class', 'label')
      .style('fill-opacity', function (d: any) {
        if (!showLabels) return 0;
        return d.parent === root || d.parent === focus ? 1 : 0;
      })
      .style('display', function (d: any) {
        if (!showLabels) return 'none';
        return d.parent === root || d.parent === focus ? 'inline' : 'none';
      })
      .text(function (d: any) {
        if (!d.data.displayName) return '';

        // Remove "CRE: " prefix
        let name = d.data.displayName.replace(/^CRE: /, '');

        // Truncate if necessary
        name = name.length > 33 ? name.substr(0, 33) + '...' : name;

        // Add count of children
        if (d.data.children && d.data.children.length > 0) {
          name += ' (' + d.data.children.length + ')';
        }

        return name;
      });

    var node = g.selectAll('circle,text');

    svg.style('background', color(-1)).on('click', function (event) {
      updateBreadcrumb(root);
      zoom(event, root);
    });

    zoomTo([root.x, root.y, root.r * 2 + margin]);
    setBreadcrumb(['Cluster']);

    //Created a new zoom function that allows toggling labels on zoom

    function zoom(event: any, d: any) {
      var focus0 = focus;
      focus = d;

      var transition = d3
        .transition()
        .duration(event.altKey ? 7500 : 750)
        .tween('zoom', function () {
          var i = d3.interpolateZoom(view, [focus.x, focus.y, focus.r * 2 + margin]);
          return function (t) {
            zoomTo(i(t));
          };
        });

      if (showLabels) {
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
    }

    function zoomTo(v) {
      var k = diameter / v[2];
      view = v;
      viewRef.current = v;
      node.attr('transform', function (d: any) {
        return 'translate(' + (d.x - v[0]) * k + ',' + (d.y - v[1]) * k + ')';
      });
      circle.attr('r', function (d) {
        return d.r * k;
      });
    }
    rootRef.current = root;
    zoomRef.current = zoom;
    updateBreadcrumbRef.current = updateBreadcrumb;
    zoomToRef.current = zoomTo;

    // Clean up tooltip when component unmounts
    return () => {
      d3.select('.circle-tooltip').remove();
    };
  }, [useFullScreen, dataTree]);

  const defaultSize = width > height ? height - 100 : width;
  const size = useFullScreen ? width : defaultSize;

  return (
    <div style={{ position: 'relative', width: '100vw', minHeight: size + 80 }}>
      {/* Breadcrumb navigation: full width, at the top */}
      {breadcrumb.length > 0 && (
        <div
          className="breadcrumb-container"
          style={{
            margin: 0,
            marginBottom: 0,
            textAlign: 'center',
            borderRadius: '8px 8px 0 0',
            width: '100vw',
            maxWidth: '100vw',
            background: '#f8f8f8',
            boxSizing: 'border-box',
            position: 'relative',
            zIndex: 10,
          }}
        >
          {breadcrumb.map((item, index) => (
            <React.Fragment key={index}>
              {index > 0 && <span className="separator"> &gt; </span>}
              <span
                className="breadcrumb-item"
                style={{
                  cursor: index === breadcrumb.length - 1 ? 'default' : 'pointer',
                  color: index === breadcrumb.length - 1 ? '#333' : '#2185d0',
                  fontWeight: index === breadcrumb.length - 1 ? 'bold' : 500,
                  textDecoration: index === breadcrumb.length - 1 ? 'none' : 'underline',
                }}
                onClick={() => {
                  if (index < breadcrumb.length - 1) {
                    let node = rootRef.current;
                    for (let i = 1; i <= index; i++) {
                      if (!node.children) break;
                      node = node.children.find(
                        (child) =>
                          child.data.displayName &&
                          child.data.displayName.replace(/^CRE: /, '') === breadcrumb[i]
                      );
                      if (!node) break;
                    }
                    if (node) {
                      updateBreadcrumbRef.current(node);
                      zoomRef.current({ altKey: false }, node);
                    }
                  }
                }}
              >
                {item}
              </span>
            </React.Fragment>
          ))}
        </div>
      )}

      {/* Graph container: absolutely positioned and centered */}
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: 60, // adjust if needed to leave space for breadcrumbs
          transform: 'translateX(-50%)',
          width: size,
          height: size,
          background: 'rgb(163, 245, 207)',
          borderRadius: 8,
          zIndex: 1,
        }}
      >
        {/* Top right fullscreen button */}
        <div
          style={{
            position: 'absolute',
            right: 0,
            top: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '5px',
            zIndex: 21,
          }}
        >
          <Button icon onClick={() => setUseFullScreen(!useFullScreen)} className="screen-size-button">
            <Icon name={useFullScreen ? 'compress' : 'expand'} />
          </Button>
        </div>
        {/* Bottom right zoom controls */}
        <div
          style={{
            position: 'absolute',
            right: 20,
            bottom: 20,
            display: 'flex',

            flexDirection: 'row',
            gap: '10px',
            zIndex: 20,
          }}
        >
          <Button
            icon
            className="screen-size-button"
            onClick={() => {
              if (!zoomToRef.current || !rootRef.current) return;

              const currentView: [number, number, number] = viewRef.current
                ? viewRef.current
                : [rootRef.current.x, rootRef.current.y, rootRef.current.r * 2 + margin];

              // To ZOOM IN, we need a LARGER scale factor, which requires a SMALLER view diameter.
              const targetView: [number, number, number] = [
                currentView[0],
                currentView[1],
                currentView[2] * 0.8,
              ];
              const i = d3.interpolateZoom(currentView, targetView);

              d3.select('svg')
                .transition()
                .duration(350)
                .tween('zoom', () => (t) => zoomToRef.current(i(t)));
            }}
          >
            <Icon name="plus" />
          </Button>
          <Button
            icon
            className="screen-size-button"
            onClick={() => {
              if (!zoomToRef.current || !rootRef.current) return;

              const currentView: [number, number, number] = viewRef.current
                ? viewRef.current
                : [rootRef.current.x, rootRef.current.y, rootRef.current.r * 2 + margin];

              // To ZOOM OUT, we need a SMALLER scale factor, which requires a LARGER view diameter.
              const targetView: [number, number, number] = [
                currentView[0],
                currentView[1],
                currentView[2] / 0.8,
              ];
              const i = d3.interpolateZoom(currentView, targetView);

              d3.select('svg')
                .transition()
                .duration(350)
                .tween('zoom', () => (t) => zoomToRef.current(i(t)));
            }}
          >
            <Icon name="minus" />
          </Button>
        </div>
        `
        <svg
          width={size}
          height={size}
          style={{ background: 'transparent', display: 'block', margin: 'auto' }}
        >
          <g transform={`translate(${size / 2},${size / 2})`}></g>
        </svg>
      </div>
      <LoadingAndErrorIndicator loading={dataLoading} error={null} />
    </div>
  );
};
