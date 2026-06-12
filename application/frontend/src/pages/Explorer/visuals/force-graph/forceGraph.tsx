import './forceGraph.scss';

import { LoadingAndErrorIndicator } from 'application/frontend/src/components/LoadingAndErrorIndicator';
import { useDataStore } from 'application/frontend/src/providers/DataProvider';
import { LinkedTreeDocument } from 'application/frontend/src/types';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph3D, { ForceGraphMethods } from 'react-force-graph-3d';
import { Checkbox, Dropdown } from 'semantic-ui-react';

interface DropdownOption {
  key: string;
  text: string;
  value: string;
  disabled?: boolean;
}

interface GraphNode {
  id: string;
  size: number;
  name: string;
  doctype: string;
  originalNodes?: any[];
  x?: number;
  y?: number;
  z?: number;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  count: number;
  type: string;
}

interface GraphPayload {
  nodes: GraphNode[];
  links: GraphLink[];
}

const relationColors: Record<string, string> = {
  contains: 'rgba(45, 212, 191, 0.55)',
  related: 'rgba(96, 165, 250, 0.55)',
  'linked to': 'rgba(196, 181, 253, 0.55)',
  same: 'rgba(251, 113, 133, 0.55)',
};

const getNodeId = (node: string | GraphNode): string =>
  typeof node === 'object' && node !== null ? node.id : String(node);

const createLinkId = (source: string | GraphNode, target: string | GraphNode, ltype: string): string => {
  const sourceId = getNodeId(source);
  const targetId = getNodeId(target);
  return `${sourceId}::${targetId}::${(ltype || '').toLowerCase()}`;
};

const getTrimmedExtent = (values: number[]): [number, number] => {
  if (!values.length) return [0, 0];

  const sorted = [...values].sort((a, b) => a - b);
  if (sorted.length < 12) {
    return [sorted[0], sorted[sorted.length - 1]];
  }

  const lowerIndex = Math.floor((sorted.length - 1) * 0.1);
  const upperIndex = Math.ceil((sorted.length - 1) * 0.9);
  return [sorted[lowerIndex], sorted[upperIndex]];
};

const getMainConnectedComponentIds = (data: GraphPayload): Set<string> => {
  const neighbors = new Map<string, Set<string>>();
  data.nodes.forEach((node) => neighbors.set(node.id, new Set()));

  data.links.forEach((link) => {
    const sourceId = getNodeId(link.source);
    const targetId = getNodeId(link.target);

    if (!neighbors.has(sourceId)) {
      neighbors.set(sourceId, new Set());
    }
    if (!neighbors.has(targetId)) {
      neighbors.set(targetId, new Set());
    }

    neighbors.get(sourceId)?.add(targetId);
    neighbors.get(targetId)?.add(sourceId);
  });

  let largest = new Set<string>();
  const visited = new Set<string>();

  neighbors.forEach((_, startId) => {
    if (visited.has(startId)) return;

    const queue = [startId];
    const current = new Set<string>();
    visited.add(startId);

    while (queue.length) {
      const nodeId = queue.pop() as string;
      current.add(nodeId);
      neighbors.get(nodeId)?.forEach((nextId) => {
        if (!visited.has(nextId)) {
          visited.add(nextId);
          queue.push(nextId);
        }
      });
    }

    if (current.size > largest.size) {
      largest = current;
    }
  });

  return largest;
};

const getStableCameraFrame = (data: GraphPayload) => {
  const primaryIds = getMainConnectedComponentIds(data);

  const validPos = (node: GraphNode) =>
    Number.isFinite(node.x) && Number.isFinite(node.y) && Number.isFinite(node.z);

  const positionedMainNodes = data.nodes.filter((node) => primaryIds.has(node.id) && validPos(node));
  const positionedAllNodes = data.nodes.filter(validPos);
  const frameNodes = positionedMainNodes.length >= 8 ? positionedMainNodes : positionedAllNodes;

  if (!frameNodes.length) {
    return null;
  }

  const xs = frameNodes.map((node) => node.x as number);
  const ys = frameNodes.map((node) => node.y as number);
  const zs = frameNodes.map((node) => node.z as number);

  const [minX, maxX] = getTrimmedExtent(xs);
  const [minY, maxY] = getTrimmedExtent(ys);
  const [minZ, maxZ] = getTrimmedExtent(zs);

  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const spanZ = Math.max(maxZ - minZ, 1);
  const rawSpanX = Math.max(Math.max(...xs) - Math.min(...xs), 1);
  const rawSpanY = Math.max(Math.max(...ys) - Math.min(...ys), 1);
  const rawSpanZ = Math.max(Math.max(...zs) - Math.min(...zs), 1);

  return {
    centerX: (minX + maxX) / 2,
    centerY: (minY + maxY) / 2,
    centerZ: (minZ + maxZ) / 2,
    maxSpan: Math.max(spanX, spanY, spanZ, 1),
    rawSpanX,
    rawSpanY,
    rawSpanZ,
    rawMaxSpan: Math.max(rawSpanX, rawSpanY, rawSpanZ, 1),
  };
};

const getCameraFitDistance = (graph: ForceGraphMethods | undefined, spanX: number, spanY: number) => {
  const camera: any = graph?.camera?.();
  const renderer: any = graph?.renderer?.();
  const width = renderer?.domElement?.clientWidth || 1920;
  const height = renderer?.domElement?.clientHeight || 1080;
  const aspect = Math.max(width / Math.max(height, 1), 0.0001);
  const fov = (((camera?.fov as number) || 40) * Math.PI) / 180;
  const halfFovTan = Math.tan(fov / 2);

  const distanceForHeight = (Math.max(spanY, 1) * 0.5) / Math.max(halfFovTan, 0.0001);
  const distanceForWidth = (Math.max(spanX, 1) * 0.5) / Math.max(halfFovTan * aspect, 0.0001);

  return Math.max(distanceForHeight, distanceForWidth, 1);
};

const alignGraphForFinalPose = (data: GraphPayload) => {
  const primaryIds = getMainConnectedComponentIds(data);
  const positionedPrimaryNodes = data.nodes.filter(
    (node) =>
      primaryIds.has(node.id) && Number.isFinite(node.x) && Number.isFinite(node.y) && Number.isFinite(node.z)
  );

  if (positionedPrimaryNodes.length < 3) {
    return;
  }

  const centerX = positionedPrimaryNodes.reduce((sum, node) => sum + (node.x as number), 0) / positionedPrimaryNodes.length;
  const centerY = positionedPrimaryNodes.reduce((sum, node) => sum + (node.y as number), 0) / positionedPrimaryNodes.length;

  let sxx = 0;
  let syy = 0;
  let sxy = 0;
  positionedPrimaryNodes.forEach((node) => {
    const dx = (node.x as number) - centerX;
    const dy = (node.y as number) - centerY;
    sxx += dx * dx;
    syy += dy * dy;
    sxy += dx * dy;
  });

  const majorAxisAngle = 0.5 * Math.atan2(2 * sxy, sxx - syy);
  const rotateBy = -majorAxisAngle;
  const cosTheta = Math.cos(rotateBy);
  const sinTheta = Math.sin(rotateBy);

  data.nodes.forEach((node) => {
    if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) return;

    const dx = (node.x as number) - centerX;
    const dy = (node.y as number) - centerY;
    node.x = centerX + dx * cosTheta - dy * sinTheta;
    node.y = centerY + dx * sinTheta + dy * cosTheta;
  });

  let leftCount = 0;
  let rightCount = 0;
  positionedPrimaryNodes.forEach((node) => {
    if ((node.x as number) < centerX) {
      leftCount += 1;
    } else {
      rightCount += 1;
    }
  });

  if (rightCount < leftCount) {
    data.nodes.forEach((node) => {
      if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) return;
      node.x = centerX - ((node.x as number) - centerX);
      node.y = centerY - ((node.y as number) - centerY);
    });
  }
};

export const ExplorerForceGraph = () => {
  const [graphData, setGraphData] = useState<GraphPayload | null>(null);
  const [ignoreTypes, setIgnoreTypes] = useState<string[]>(['same']);
  const [maxNodeSize, setMaxNodeSize] = useState(1);
  const { dataLoading, dataTree, getStoreKey, dataStore } = useDataStore();
  const fgRef = useRef<ForceGraphMethods>();
  const hoverDelayTimerRef = useRef<number | null>(null);
  const didFinalCenterRef = useRef(false);

  const [filterTypeA, setFilterTypeA] = useState('');
  const [filterTypeB, setFilterTypeB] = useState('');
  const [showAll, setShowAll] = useState(true);

  const [creOptions, setCreOptions] = useState<DropdownOption[]>([]);
  const [combinedOptions, setCombinedOptions] = useState<DropdownOption[]>([]);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const [focusedNodeIds, setFocusedNodeIds] = useState<Set<string>>(new Set());
  const [focusedLinkIds, setFocusedLinkIds] = useState<Set<string>>(new Set());

  const getBaseName = (standardId: string): string => standardId.split(':')[0];
  const getGroupedStandardId = (baseName: string): string => `grouped_${baseName}`;
  const getBaseNameFromGrouped = (groupedId: string): string => groupedId.replace('grouped_', '');

  const getLinkBaseColor = (ltype: string) => relationColors[ltype.toLowerCase()] || 'rgba(148, 163, 184, 0.45)';

  const getNodeBaseColor = (doctype: string) => {
    switch ((doctype || '').toLowerCase()) {
      case 'cre':
        return '#93c5fd';
      case 'standard':
        return '#f59e0b';
      case 'tool':
        return '#86efac';
      default:
        return '#c4b5fd';
    }
  };

  const adjacency = useMemo(() => {
    const neighborNodes = new Map<string, Set<string>>();
    const incidentLinks = new Map<string, Set<string>>();

    if (!graphData) {
      return { neighborNodes, incidentLinks };
    }

    graphData.links.forEach((link) => {
      const sourceId = getNodeId(link.source);
      const targetId = getNodeId(link.target);
      const linkId = createLinkId(sourceId, targetId, link.type);

      if (!neighborNodes.has(sourceId)) {
        neighborNodes.set(sourceId, new Set());
      }
      if (!neighborNodes.has(targetId)) {
        neighborNodes.set(targetId, new Set());
      }
      neighborNodes.get(sourceId)?.add(targetId);
      neighborNodes.get(targetId)?.add(sourceId);

      if (!incidentLinks.has(sourceId)) {
        incidentLinks.set(sourceId, new Set());
      }
      if (!incidentLinks.has(targetId)) {
        incidentLinks.set(targetId, new Set());
      }
      incidentLinks.get(sourceId)?.add(linkId);
      incidentLinks.get(targetId)?.add(linkId);
    });

    return { neighborNodes, incidentLinks };
  }, [graphData]);

  const clearDelayedFocus = () => {
    if (hoverDelayTimerRef.current) {
      window.clearTimeout(hoverDelayTimerRef.current);
      hoverDelayTimerRef.current = null;
    }
    setFocusedNodeId(null);
    setFocusedNodeIds(new Set());
    setFocusedLinkIds(new Set());
  };

  const handleNodeHover = (node: GraphNode | null) => {
    if (hoverDelayTimerRef.current) {
      window.clearTimeout(hoverDelayTimerRef.current);
      hoverDelayTimerRef.current = null;
    }

    if (!node) {
      clearDelayedFocus();
      return;
    }

    setFocusedNodeId(null);
    setFocusedNodeIds(new Set());
    setFocusedLinkIds(new Set());

    const hoveredId = node.id;
    hoverDelayTimerRef.current = window.setTimeout(() => {
      const neighbors = adjacency.neighborNodes.get(hoveredId) || new Set<string>();
      const links = adjacency.incidentLinks.get(hoveredId) || new Set<string>();
      const nextFocusedNodes = new Set<string>([hoveredId, ...neighbors]);
      const nextFocusedLinks = new Set<string>(links);

      setFocusedNodeId(hoveredId);
      setFocusedNodeIds(nextFocusedNodes);
      setFocusedLinkIds(nextFocusedLinks);
      hoverDelayTimerRef.current = null;
    }, 1000);
  };

  const getRenderedNodeColor = (node: GraphNode) => {
    const baseColor = getNodeBaseColor(node.doctype);
    if (!focusedNodeId) return baseColor;
    if (!focusedNodeIds.has(node.id)) return 'rgba(148, 163, 184, 0.16)';
    if (node.id === focusedNodeId) return '#ffffff';
    return baseColor;
  };

  const isFocusedLink = (link: GraphLink) => {
    const linkId = createLinkId(link.source, link.target, link.type);
    return focusedLinkIds.has(linkId);
  };

  const getRenderedLinkColor = (link: GraphLink) => {
    if (!focusedNodeId) return getLinkBaseColor(link.type);
    return isFocusedLink(link) ? getLinkBaseColor(link.type) : 'rgba(148, 163, 184, 0.05)';
  };

  const getRenderedLinkWidth = (link: GraphLink) => {
    if (!focusedNodeId) return 5;
    return isFocusedLink(link) ? 5 : 1;
  };

  useEffect(() => {
    const creList: DropdownOption[] = Object.values(dataStore)
      .filter((n) => n.doctype === 'CRE')
      .map((n) => ({
        key: n.id,
        text: n.displayName,
        value: n.id,
      }));

    setCreOptions([
      { key: 'none_typeA', text: 'None', value: '' },
      { key: 'all_cre', text: 'ALL CREs', value: 'all_cre' },
      ...creList,
    ]);
  }, [dataStore]);

  useEffect(() => {
    const gData: GraphPayload = {
      nodes: [],
      links: [],
    };

    const allNodes = Object.values(dataStore);
    if (!allNodes.length) {
      setGraphData(null);
      return;
    }

    function collectStandards(node: any, standards: any[] = []): any[] {
      if (node.doctype && node.doctype.toLowerCase() === 'standard') {
        standards.push(node);
      }
      if (node.links && Array.isArray(node.links)) {
        node.links.forEach((link: any) => {
          if (link.document) {
            collectStandards(link.document, standards);
          }
        });
      }
      return standards;
    }

    let allStandardNodes: any[] = [];
    dataTree.forEach((rootNode: any) => {
      allStandardNodes = allStandardNodes.concat(collectStandards(rootNode));
    });

    const groupedStandards = new Map<string, any[]>();
    allStandardNodes.forEach((node: any) => {
      const baseName = getBaseName(node.id);
      if (!groupedStandards.has(baseName)) {
        groupedStandards.set(baseName, []);
      }
      groupedStandards.get(baseName)?.push(node);
    });

    const originalToGroupedMap = new Map<string, string>();
    groupedStandards.forEach((nodes, baseName) => {
      const groupedId = getGroupedStandardId(baseName);
      nodes.forEach((node) => {
        originalToGroupedMap.set(node.id, groupedId);
      });
    });

    const standardDropdownOptions: DropdownOption[] = Array.from(groupedStandards.entries()).map(
      ([baseName, group]) => ({
        key: getGroupedStandardId(baseName),
        text: `${baseName} (${group.length})`,
        value: getGroupedStandardId(baseName),
      })
    );

    const isAll = (val: string) => val && val.startsWith('all_');
    const isGroupedStandard = (val: string) => val && val.startsWith('grouped_');
    const getTypeFromAll = (val: string) => val.replace('all_', '');

    const matchesFilter = (node: any, filterVal: string): boolean => {
      if (!filterVal || filterVal === '') return true;

      if (isAll(filterVal)) {
        const type = getTypeFromAll(filterVal);
        return (node.doctype || '').toLowerCase() === type.toLowerCase();
      }

      if (isGroupedStandard(filterVal)) {
        const baseName = getBaseNameFromGrouped(filterVal);
        return (node.doctype || '').toLowerCase() === 'standard' && getBaseName(node.id) === baseName;
      }

      return node.id === filterVal;
    };

    const traversalSeen = new Set<string>();
    const linkSeen = new Set<string>();

    const populateGraphData = (node: any) => {
      const traversalKey = getStoreKey(node);
      if (traversalSeen.has(traversalKey)) {
        return;
      }
      traversalSeen.add(traversalKey);

      if (node.links && Array.isArray(node.links)) {
        node.links.forEach((x: LinkedTreeDocument) => {
          if (x.document && !ignoreTypes.includes(x.ltype.toLowerCase())) {
            const sourceKey =
              (node.doctype || '').toLowerCase() === 'standard'
                ? originalToGroupedMap.get(node.id) || getStoreKey(node)
                : getStoreKey(node);
            const targetKey =
              (x.document.doctype || '').toLowerCase() === 'standard'
                ? originalToGroupedMap.get(x.document.id) || getStoreKey(x.document)
                : getStoreKey(x.document);

            const linkId = createLinkId(sourceKey, targetKey, x.ltype);
            if (!linkSeen.has(linkId)) {
              linkSeen.add(linkId);
              gData.links.push({
                source: sourceKey,
                target: targetKey,
                count: x.ltype === 'Contains' ? 2 : 1,
                type: x.ltype,
              });
            }

            populateGraphData(x.document);
          }
        });
      }
    };

    dataTree.forEach((x) => populateGraphData(x));

    if (!showAll && (filterTypeA || filterTypeB)) {
      gData.links = gData.links.filter((link: GraphLink) => {
        let sourceNode = dataStore[getNodeId(link.source)];
        let targetNode = dataStore[getNodeId(link.target)];

        if (getNodeId(link.source).startsWith('grouped_')) {
          const baseName = getBaseNameFromGrouped(getNodeId(link.source));
          sourceNode = {
            id: getNodeId(link.source),
            doctype: 'standard',
            displayName: baseName,
            links: [],
            url: '',
            name: baseName,
          };
        }

        if (getNodeId(link.target).startsWith('grouped_')) {
          const baseName = getBaseNameFromGrouped(getNodeId(link.target));
          targetNode = {
            id: getNodeId(link.target),
            doctype: 'standard',
            displayName: baseName,
            links: [],
            url: '',
            name: baseName,
          };
        }

        if (!sourceNode || !targetNode) return false;

        const sourceMatchesA = matchesFilter(sourceNode, filterTypeA);
        const sourceMatchesB = matchesFilter(sourceNode, filterTypeB);
        const targetMatchesA = matchesFilter(targetNode, filterTypeA);
        const targetMatchesB = matchesFilter(targetNode, filterTypeB);

        return sourceMatchesA || sourceMatchesB || targetMatchesA || targetMatchesB;
      });
    }

    const nodesMap: Record<string, GraphNode> = {};
    const addNode = (name: string) => {
      if (!nodesMap[name]) {
        if (name.startsWith('grouped_')) {
          const baseName = getBaseNameFromGrouped(name);
          const groupedNodes = groupedStandards.get(baseName) || [];

          nodesMap[name] = {
            id: name,
            size: groupedNodes.length || 1,
            name: baseName,
            doctype: 'standard',
            originalNodes: groupedNodes,
          };
        } else {
          const storedDoc = dataStore[name];
          nodesMap[name] = {
            id: name,
            size: 1,
            name: storedDoc ? storedDoc.displayName : name,
            doctype: storedDoc ? storedDoc.doctype : 'Unknown',
          };
        }
        gData.nodes.push(nodesMap[name]);
      } else {
        nodesMap[name].size += 1;
      }
    };

    gData.links.forEach((link) => {
      addNode(getNodeId(link.source));
      addNode(getNodeId(link.target));
    });

    const combined: DropdownOption[] = [
      { key: 'none_typeB', text: 'None', value: '' },
      { key: 'all_standard', text: 'ALL Standards', value: 'all_standard' },
      { key: 'separator1', text: '─ Standards ─', value: '', disabled: true },
      ...standardDropdownOptions,
      { key: 'separator2', text: '─ CREs ─', value: '', disabled: true },
      { key: 'all_cre_right', text: 'ALL CREs', value: 'all_cre' },
      ...Object.values(dataStore)
        .filter((n) => n.doctype === 'CRE')
        .map((n) => ({
          key: `${n.id}_right`,
          text: n.displayName,
          value: n.id,
        })),
    ];

    setCombinedOptions(combined);

    const peakNodeSize = gData.nodes.reduce((acc, node) => Math.max(acc, node.size), 1);
    setMaxNodeSize(peakNodeSize);

    const reversedLinks = gData.links.map((l) => ({
      source: l.target,
      target: l.source,
      count: l.count,
      type: l.type,
    }));

    setGraphData({ nodes: gData.nodes, links: reversedLinks });
  }, [ignoreTypes, dataTree, filterTypeA, filterTypeB, showAll, dataStore, getStoreKey]);

  const toggleLinks = (name: string) => {
    const ignoreTypesClone = structuredClone(ignoreTypes);
    if (ignoreTypesClone.includes(name)) {
      const index = ignoreTypesClone.indexOf(name);
      ignoreTypesClone.splice(index, 1);
      setIgnoreTypes(ignoreTypesClone);
    } else {
      ignoreTypesClone.push(name);
      setIgnoreTypes(ignoreTypesClone);
    }
  };

  useEffect(() => {
    if (!graphData || !fgRef.current) return;
    didFinalCenterRef.current = false;

    const controls: any = fgRef.current.controls?.();
    if (controls) {
      controls.enableDamping = true;
      controls.dampingFactor = 0.12;
      controls.enablePan = false;
      controls.enableRotate = true;
      controls.enableZoom = true;
      controls.rotateSpeed = 0.85;
      controls.zoomSpeed = 1;
      controls.minDistance = 90;
      controls.maxDistance = 5200;
    }

    // Start tight
    fgRef.current.d3Force('charge')?.strength(-55);

    // Expand
    const expandTimer = window.setTimeout(() => {
      fgRef.current?.d3Force('charge')?.strength(-75);
      fgRef.current?.d3ReheatSimulation();
    }, 200);

    // Settle
    const settleTimer = window.setTimeout(() => {
      fgRef.current?.d3Force('charge')?.strength(-95);
      fgRef.current?.d3ReheatSimulation();
    }, 620);

    return () => {
      window.clearTimeout(expandTimer);
      window.clearTimeout(settleTimer);
    };
  }, [graphData]);

  useEffect(() => {
    return () => {
      if (hoverDelayTimerRef.current) {
        window.clearTimeout(hoverDelayTimerRef.current);
      }
    };
  }, []);

  return (
    <main className="explorer-force-graph-page">
      <LoadingAndErrorIndicator loading={dataLoading} error={null} />

      <section className="explorer-force-graph-controls">
        <div className="explorer-force-graph-controls__toggles">
          <Checkbox
            className="graph-chip graph-chip--contains"
            label="Contains"
            checked={!ignoreTypes.includes('contains')}
            onChange={() => toggleLinks('contains')}
          />
          <Checkbox
            className="graph-chip graph-chip--related"
            label="Related"
            checked={!ignoreTypes.includes('related')}
            onChange={() => toggleLinks('related')}
          />
          <Checkbox
            className="graph-chip graph-chip--linked"
            label="Linked To"
            checked={!ignoreTypes.includes('linked to')}
            onChange={() => toggleLinks('linked to')}
          />
          <Checkbox
            className="graph-chip graph-chip--same"
            label="Same"
            checked={!ignoreTypes.includes('same')}
            onChange={() => toggleLinks('same')}
          />
        </div>

        <div className="explorer-force-graph-controls__filters">
          <Dropdown
            className="graph-select"
            placeholder="Select CRE"
            options={creOptions}
            value={filterTypeA}
            onChange={(e, data) => setFilterTypeA((data.value ?? '') as string)}
            selection
            search
          />
          <Dropdown
            className="graph-select graph-select--wide"
            placeholder="Select Standard or CRE"
            options={combinedOptions}
            value={filterTypeB}
            onChange={(e, data) => setFilterTypeB((data.value ?? '') as string)}
            selection
            search
          />
          <Checkbox
            className="graph-chip graph-chip--all"
            label="Show All"
            checked={showAll}
            onChange={() => setShowAll(!showAll)}
          />
        </div>

        <div className="explorer-force-graph-controls__meta">
          <span>
            <strong>{graphData?.nodes.length || 0}</strong> nodes
          </span>
          <span>
            <strong>{graphData?.links.length || 0}</strong> connections
          </span>
          <span>{focusedNodeId ? 'Focused neighborhood' : 'Hover 1s on a node to spotlight neighbors'}</span>
        </div>
      </section>

      <section className="explorer-force-graph-canvas">
        {showAll || filterTypeA || filterTypeB ? (
          graphData && (
            <ForceGraph3D
              ref={fgRef}
              graphData={graphData}
              controlType="orbit"
              enableNodeDrag={false}
              backgroundColor="#02050d"
              nodeRelSize={6.32}
              nodeVal={(n: any) => Math.max((14 * (n.size || 1)) / maxNodeSize, 0.8)}
              nodeLabel={(n: any) => `${n.name} (${n.size})`}
              nodeColor={(n: any) => getRenderedNodeColor(n)}
              linkColor={(l: any) => getRenderedLinkColor(l)}
              linkWidth={(l: any) => getRenderedLinkWidth(l)}
              linkOpacity={focusedNodeId ? 1 : 0.25}
              warmupTicks={0}
              cooldownTicks={100}
              d3VelocityDecay={0.32}
              d3AlphaDecay={0.032}
              onNodeHover={(node: any) => handleNodeHover(node)}
              onBackgroundClick={clearDelayedFocus}
              onEngineStop={() => {
                if (didFinalCenterRef.current || !fgRef.current) return;
                if (graphData) {
                  alignGraphForFinalPose(graphData);
                  (fgRef.current as any).refresh?.();
                }
                const stableFrame = graphData ? getStableCameraFrame(graphData) : null;

                if (stableFrame) {
                  const { centerX, centerY, centerZ, rawSpanX, rawSpanY } = stableFrame;
                  const lookAtX = centerX + rawSpanX * 0.02;
                  const lookAtY = centerY - rawSpanY * 0.035;
                  const baseDistance = getCameraFitDistance(fgRef.current, rawSpanX, rawSpanY);
                  const settleDistance = Math.min(Math.max(baseDistance * 1.66, 1200), 2550);
                  const cameraY = lookAtY + rawSpanY * 0.017;

                  fgRef.current.cameraPosition(
                    {
                      x: lookAtX,
                      y: cameraY,
                      z: centerZ + settleDistance,
                    },
                    {
                      x: lookAtX,
                      y: lookAtY,
                      z: centerZ,
                    },
                    900
                  );

                  const orbitControls: any = fgRef.current.controls?.();
                  orbitControls.minDistance = Math.min(Math.max(settleDistance * 0.36, 150), 420);
                  orbitControls.maxDistance = Math.max(settleDistance * 6.8, 3600);
                  orbitControls?.target?.set?.(lookAtX, lookAtY, centerZ);
                  orbitControls?.update?.();
                } else {
                  fgRef.current.zoomToFit(850, 80);
                }
                didFinalCenterRef.current = true;
              }}
            />
          )
        ) : (
          <div className="explorer-force-graph-empty">
            Please select at least one filter to view the graph or enable "Show All".
          </div>
        )}

        <aside className="explorer-force-graph-legend" aria-hidden="true">
          <div className="legend-row">
            <span className="legend-swatch legend-swatch--contains"></span>
            <span>Contains</span>
          </div>
          <div className="legend-row">
            <span className="legend-swatch legend-swatch--related"></span>
            <span>Related</span>
          </div>
          <div className="legend-row">
            <span className="legend-swatch legend-swatch--linked"></span>
            <span>Linked To</span>
          </div>
          <div className="legend-row">
            <span className="legend-swatch legend-swatch--same"></span>
            <span>Same</span>
          </div>
        </aside>
      </section>
    </main>
  );
};
