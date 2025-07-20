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
        setBreadcrumb([]);
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
      .on('mouseover', function(event, d: any) {
        if (d.data.displayName) {
          // Remove "CRE: " prefix if it exists
          const displayName = d.data.displayName.replace(/^CRE: /, '');
          
          // Show full label without truncation
          tooltip
            .html(displayName + (d.data.children && d.data.children.length > 0 ? ' (' + d.data.children.length + ')' : ''))
            .style('visibility', 'visible')
            .style('top', (event.pageY - 10) + 'px')
            .style('left', (event.pageX + 10) + 'px');
        }
      })
      .on('mousemove', function(event) {
        tooltip
          .style('top', (event.pageY - 10) + 'px')
          .style('left', (event.pageX + 10) + 'px');
      })
      .on('mouseout', function() {
        tooltip.style('visibility', 'hidden');
      })
      .on('click', function (event, d: any) {
        if (focus !== d) {
          updateBreadcrumb(d);
          zoom(event, d);
          event.stopPropagation();
        }
      });

    var text = g
      .selectAll('text')
      .data(nodes)
      .enter()
      .append('text')
      .attr('class', 'label')
      .style('fill-opacity', function (d: any) {
        // Show text at all zoom levels
        return d.parent === root || (d.parent === focus) ? 1 : 0;
      })
      .style('display', function (d: any) {
        // Try to display all labels if there's room
        return d.parent === root || (d.parent === focus) ? 'inline' : 'none';
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
          // Show text for all nodes that are children of the current focus
          return (d && d.parent === focus) || el.style.display === 'inline';
        })
        .style('fill-opacity', function (d: any) {
          // Show text at all zoom levels, including deepest
          return (d && d.parent === focus) ? 1 : 0;
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

    // Clean up tooltip when component unmounts
    return () => {
      d3.select('.circle-tooltip').remove();
    };
  }, [useFullScreen, dataTree]);

  const defaultSize = width > height ? height - 100 : width;
  const size = useFullScreen ? width : defaultSize;
  
  return (
    <div>
      <LoadingAndErrorIndicator loading={dataLoading} error={null} />
      
      {/* Breadcrumb navigation */}
      {breadcrumb.length > 0 && (
        <div className="breadcrumb-container" style={{ margin: '10px auto', width: 'fit-content', textAlign: 'center' }}>
          {breadcrumb.map((item, index) => (
            <React.Fragment key={index}>
              {index > 0 && <span> &gt; </span>}
              <span>{item}</span>
            </React.Fragment>
          ))}
        </div>
      )}
      
      <div style={{ display: 'block', margin: 'auto', width: 'fit-content' }}>
        <div style={{ position: 'relative' }}>
          {/* Zoom control buttons */}
          <div style={{ position: 'absolute', right: 0, top: 0, display: 'flex', flexDirection: 'column', gap: '5px' }}>
            <Button icon onClick={() => setUseFullScreen(!useFullScreen)} className="screen-size-button">
              <Icon name={useFullScreen ? 'compress' : 'expand'} />
            </Button>
            
            {/* Zoom out button */}
            <Button 
              icon 
              className="screen-size-button" 
              onClick={() => {
                const svgElement = document.querySelector('svg');
                if (svgElement) {
                  svgElement.dispatchEvent(new Event('click'));
                }
              }}
            >
              <Icon name="minus" />
            </Button>
          </div>
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
