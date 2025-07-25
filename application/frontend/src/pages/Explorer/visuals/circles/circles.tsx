import './circles.scss';

import { LoadingAndErrorIndicator } from 'application/frontend/src/components/LoadingAndErrorIndicator';
import useWindowDimensions from 'application/frontend/src/hooks/useWindowDimensions';
import { useDataStore } from 'application/frontend/src/providers/DataProvider';
import * as d3 from 'd3';
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Button, Icon, Checkbox } from 'semantic-ui-react';

export const ExplorerCircles = () => {
  const { height, width } = useWindowDimensions();
  const [useFullScreen, setUseFullScreen] = useState(false);
  const [isInBrowserFullscreen, setIsInBrowserFullscreen] = useState(false);
  const [showLabels, setShowLabels] = useState(true);
  const { dataLoading, dataTree } = useDataStore();
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
const [breadcrumb, setBreadcrumb] = useState<string[]>([]);

  // References to store values that need to persist between renders
  const rootRef = useRef<any>(null);
  const zoomRef = useRef<any>(null);
  const updateBreadcrumbRef = useRef<any>(null);
  const zoomToRef = useRef<any>(null);
  const viewRef = useRef<[number, number, number]>([0, 0, 0]);
  const labelOffsetsRef = useRef<Map<any, number>>(new Map());

  // Track fullscreen changes
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsInBrowserFullscreen(!!document.fullscreenElement);
      // When exiting fullscreen, ensure our internal state matches
      if (!document.fullscreenElement && useFullScreen) {
        setUseFullScreen(false);
      }
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
    document.addEventListener('mozfullscreenchange', handleFullscreenChange);
    document.addEventListener('MSFullscreenChange', handleFullscreenChange);

    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
      document.removeEventListener('webkitfullscreenchange', handleFullscreenChange);
      document.removeEventListener('mozfullscreenchange', handleFullscreenChange);
      document.removeEventListener('MSFullscreenChange', handleFullscreenChange);
    };
  }, [useFullScreen]);

  // Toggle fullscreen
  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return;
    
    if (!isInBrowserFullscreen) {
      // Enter fullscreen
      if (containerRef.current.requestFullscreen) {
        containerRef.current.requestFullscreen();
      } else if ((containerRef.current as any).webkitRequestFullscreen) {
        (containerRef.current as any).webkitRequestFullscreen();
      } else if ((containerRef.current as any).mozRequestFullScreen) {
        (containerRef.current as any).mozRequestFullScreen();
      } else if ((containerRef.current as any).msRequestFullscreen) {
        (containerRef.current as any).msRequestFullscreen();
      }
      
      setUseFullScreen(true);
    } else {
      // Exit fullscreen
      if (document.exitFullscreen) {
        document.exitFullscreen();
      } else if ((document as any).webkitExitFullscreen) {
        (document as any).webkitExitFullscreen();
      } else if ((document as any).mozCancelFullScreen) {
        (document as any).mozCancelFullScreen();
      } else if ((document as any).msExitFullscreen) {
        (document as any).msExitFullscreen();
      }
      
      setUseFullScreen(false);
    }
  }, [isInBrowserFullscreen]);

  // Calculate appropriate size with constraints
  const calculateSize = () => {
    // In fullscreen mode, use the entire available space with small margins
    if (isInBrowserFullscreen) {
      return Math.min(window.innerWidth - 40, window.innerHeight - 120);
    }
    
    // Normal mode - use reasonable default with constraints
    const footerSpacing = 100;
    let calculatedSize = useFullScreen 
      ? Math.min(width - 40, height - 150 - footerSpacing)  // Full screen mode within page
      : Math.min(Math.min(height - 150 - footerSpacing, width - 40), 750); // Normal mode with cap
    
    return Math.max(calculatedSize, 300);
  };

  const size = calculateSize();

  useEffect(() => {
    var svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const margin = 20;
    // Add padding for labels
    const labelPadding = 20; 
    var diameter = +svg.attr('width') || size;
    var g = svg.append('g').attr('transform', 'translate(' + diameter / 2 + ',' + diameter / 2 + ')');

    var color = d3
      .scaleLinear<string>([-1, 5], ['hsl(152,80%,80%)', 'hsl(228,30%,40%)'])
      .interpolate(d3.interpolateHcl);

    var pack = d3
      .pack()
      .size([diameter - margin - labelPadding, diameter - margin - labelPadding])
      .padding(2);

    const populateChildren = (node: any) => {
      node.children = [];
      if (node.links) {
        node.children = node.links.filter((x: any) => x.document && x.ltype !== 'Related').map((x: any) => x.document);
      }
      node.children.forEach((x: any) => populateChildren(x));
      node.children.forEach((x: any) => {
        if (x.children.length === 0) x.size = 1;
      });
    };

    const dataTreeClone = structuredClone(dataTree);
    dataTreeClone.forEach((node: any) => populateChildren(node));

    let root: any = {
      displayName: 'OpenCRE',
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

    var focus: any = root;
    var nodes = pack(root).descendants();
    var view: [number, number, number] = [root.x, root.y, root.r * 2 + margin];

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

    // Create separate groups for circles and labels
    const circlesGroup = g.append("g").attr("class", "circles-group");
    const labelsGroup = g.append("g").attr("class", "labels-group");

    var circle = circlesGroup
      .selectAll('circle')
      .data(nodes)
      .enter()
      .append('circle')
      .attr('class', function (d: any) {
        return d.parent ? (d.children ? 'node' : 'node node--leaf') : 'node node--root';
      })
      .style('fill', function (d: any) {
        return d.children ? color(d.depth) : d.data.color ? d.data.color : null;
      })
      //New mouseover to use id if displayName is not present (most likely for white dots)
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

    // Using the showLabels state value
    const labelsVisible = showLabels;

    // Create a map to store label offset ratios for consistent positioning during zoom
    const labelOffsets = new Map();

    var text = labelsGroup
      .selectAll('text')
      .data(nodes)
      .enter()
      .append('text')
      .attr('class', function(d: any) {
        return d.parent 
          ? (d.children ? 'label label--parent' : 'label label--leaf') 
          : 'label label--root';
      })
      .style('opacity', function (d: any) {
        if (!labelsVisible) return 0;
        // Only show labels for clusters (parent nodes) and focus node's children
        return d.parent === root || d === focus || d.parent === focus ? 1 : 0;
      })
      .style('display', function (d: any) {
        if (!labelsVisible) return 'none';
        return d.parent === root || d === focus || d.parent === focus ? 'inline' : 'none';
      })
      .style('pointer-events', 'none') // Prevent labels from intercepting clicks
      .style('text-anchor', 'middle') // Center text horizontally
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
      })
      .each(function(d: any) {
        // Calculate and store the fixed vertical offset for this label
        // Move the root label further up
        const offset = d.depth === 0 ? -d.r - 30 : -d.r - 10;
        labelOffsets.set(d, offset);
        
        // Apply label collision avoidance for parent nodes only
        if (d.depth === 1) {
          const textElement = d3.select(this);
          const textWidth = (this as SVGTextElement).getComputedTextLength();
          
          // Check if label would go beyond circle bounds
          if (textWidth > d.r * 2) {
            // Truncate text if needed
            let name = d.data.displayName.replace(/^CRE: /, '');
            let shortened = name;
            let count = '';
            
            if (d.data.children && d.data.children.length > 0) {
              count = ' (' + d.data.children.length + ')';
            }
            
            // Iteratively shorten until it fits
            while ((shortened + count).length > 10 && 
                  (this as SVGTextElement).getComputedTextLength() > d.r * 2) {
              shortened = shortened.slice(0, -1);
              textElement.text(shortened + '...' + count);
            }
          }
        }
      });

    // Save reference to label offsets for use in other functions
    labelOffsetsRef.current = labelOffsets;

    svg.style('background', color(-1)).on('click', function (event) {
      updateBreadcrumb(root);
      zoom(event, root);
    });

    function zoomTo(v: [number, number, number]) {
      var k = diameter / v[2];
      view = v;
      viewRef.current = v;
      
      // Transform circles
      circle.attr('transform', function (d: any) {
        return 'translate(' + (d.x - v[0]) * k + ',' + (d.y - v[1]) * k + ')';
      }).attr('r', function (d: any) {
        return d.r * k;
      });

      // Position labels separately to maintain stable position above circles
      text.attr('transform', function (d: any) {
        return 'translate(' + (d.x - v[0]) * k + ',' + (d.y - v[1]) * k + ')';
      }).attr('dy', function (d: any) {
        // Use stored offset to maintain consistent position
        const offset = labelOffsets.get(d);
        return offset ? offset * (k / 2) : -d.r * k - 10;
      }).style('font-size', function(d: any) {
        // Keep font size proportional but constrained
        const size = Math.max(9, Math.min(13, 11 * Math.sqrt(k) * 0.5));
        return size + "px";
      });
    }

    function zoom(event: any, d: any) {
      focus = d;

      var transition = d3
        .transition()
        .duration(event.altKey ? 7500 : 750)
        .tween('zoom', function () {
          // Calculate appropriate zoom target
          var i = d3.interpolateZoom(view, [focus.x, focus.y, focus.r * 2 + margin / 3]);

          return function (t: number) {
            zoomTo(i(t));
          };
        });

      // Update label visibility based on zoom target
      transition
        .selectAll('text')
        .filter(function (d: any) {
          const el = this as HTMLElement;
          // Keep visible: 1) Labels in current focus, 2) Already visible labels
          return (labelsVisible && (d.parent === focus || d === focus)) || el.style.display === 'inline';
        })
        .style('opacity', function (d: any) {
          // Fade in labels for current focus and its children
          return (labelsVisible && (d.parent === focus || d === focus)) ? 1 : 0;
        })
        .on('start', function (d: any) {
          const el = this as HTMLElement;
          // Show labels for current focus level at start of transition
          if (labelsVisible && (d.parent === focus || d === focus)) {
            el.style.display = 'inline';
          }
        })
        .on('end', function (d: any) {
          const el = this as HTMLElement;
          // Hide labels that are not in current focus level after transition
          if (!labelsVisible || (d.parent !== focus && d !== focus)) {
            el.style.display = 'none';
          }
        });
    }

    zoomTo([root.x, root.y, root.r * 2 + margin]);
    setBreadcrumb(['Cluster']);

    // Store references for use in event handlers
    rootRef.current = root;
    zoomRef.current = zoom;
    updateBreadcrumbRef.current = updateBreadcrumb;
    zoomToRef.current = zoomTo;

    // Clean up tooltip when component unmounts
    return () => {
      d3.select('.circle-tooltip').remove();
    };
  }, [useFullScreen, dataTree, width, height, showLabels, size, isInBrowserFullscreen]);

  return (
    <div 
      ref={containerRef}
      className="explorer-container" 
      style={{ 
        position: 'relative', 
        width: '100%',
        // Set defined height with additional footer margin 
        minHeight: size + 150,
        // Add padding at the bottom for footer space
        paddingBottom: '100px',
        marginBottom: '30px',
        overflow: 'visible'
      }}
    >
  {/* Breadcrumb navigation: full width, at the top */}
  {breadcrumb.length > 0 && (
    <div
      className="breadcrumb-container"
      style={{
        margin: 0,
            marginBottom: '10px',
        textAlign: 'center',
        borderRadius: '8px 8px 0 0',
            width: '100%',
        background: '#f8f8f8',
        boxSizing: 'border-box',
        position: 'relative',
            zIndex: 10
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
                  textDecoration: index === breadcrumb.length - 1 ? 'none' : 'underline'
            }}
            onClick={() => {
              if (index < breadcrumb.length - 1) {
                let node = rootRef.current;
                for (let i = 1; i <= index; i++) {
                  if (!node.children) break;
                  node = node.children.find(
                        (child: any) =>
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

      {/* Graph container: centered div instead of absolute positioning */}
  <div
    style={{
          margin: '0 auto',
      width: size,
      height: size,
      background: 'rgb(163, 245, 207)',
      borderRadius: 8,
          position: 'relative',
          zIndex: 1
    }}
  >
    {/* Show Labels Checkbox: top left corner inside graph area */}
    <div
      style={{
        position: 'absolute',
        left: 10,
        top: 10,
        zIndex: 100,
        background: 'white',
        padding: '5px 10px',
        borderRadius: '8px',
            boxShadow: '0 1px 4px rgba(0,0,0,0.1)'
      }}
    >
      <Checkbox
        toggle
        label="Show Labels"
        checked={showLabels}
        onChange={() => setShowLabels(!showLabels)}
      />
    </div>

        {/* Top right fullscreen button */}
    <div
      style={{
        position: 'absolute',
            right: 10,
            top: 10,
        display: 'flex',
        flexDirection: 'column',
        gap: '5px',
            zIndex: 21
      }}
    >
          <Button 
            icon
            onClick={toggleFullscreen} 
            className="screen-size-button"
          >
            <Icon name={isInBrowserFullscreen ? 'compress' : 'expand'} />
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
            zIndex: 20
          }}
        >
          <Button
            icon
            className="screen-size-button"
            onClick={() => {
              if (!zoomToRef.current || !rootRef.current) return;

              const margin = 20;
              const currentView: [number, number, number] = viewRef.current
                ? viewRef.current
                : [rootRef.current.x, rootRef.current.y, rootRef.current.r * 2 + margin];

              // To ZOOM IN, we need a LARGER scale factor, which requires a SMALLER view diameter.
              const targetView: [number, number, number] = [
                currentView[0],
                currentView[1],
                currentView[2] * 0.7 // More aggressive zoom
              ];
              const i = d3.interpolateZoom(currentView, targetView);

              d3.select('svg')
                .transition()
                .duration(350)
                .tween('zoom', () => (t: number) => zoomToRef.current(i(t)));
            }}
          >
            <Icon name="plus" />
          </Button>
          <Button
            icon
            className="screen-size-button"
            onClick={() => {
              if (!zoomToRef.current || !rootRef.current) return;

              const margin = 20;
              const currentView: [number, number, number] = viewRef.current
                ? viewRef.current
                : [rootRef.current.x, rootRef.current.y, rootRef.current.r * 2 + margin];

              // To ZOOM OUT, we need a SMALLER scale factor, which requires a LARGER view diameter.
              const targetView: [number, number, number] = [
                currentView[0],
                currentView[1],
                currentView[2] / 0.7 // More aggressive zoom
              ];
              const i = d3.interpolateZoom(currentView, targetView);

              d3.select('svg')
                .transition()
                .duration(350)
                .tween('zoom', () => (t: number) => zoomToRef.current(i(t)));
            }}
          >
            <Icon name="minus" />
          </Button>
        </div>
        
        <svg
          ref={svgRef}
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
