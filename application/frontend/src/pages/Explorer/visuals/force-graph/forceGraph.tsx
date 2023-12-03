import './forceGraph.scss';

import { LoadingAndErrorIndicator } from 'application/frontend/src/components/LoadingAndErrorIndicator';
import { useDataStore } from 'application/frontend/src/providers/DataProvider';
import { LinkedTreeDocument } from 'application/frontend/src/types';
import { lab } from 'd3';
import React, { useEffect, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { Checkbox, Form } from 'semantic-ui-react';

export const ExplorerForceGraph = () => {
  const [graphData, setGraphData] = useState({
         nodes: [
          {id:'core-requirements', name: 'Requirements', fx: 15, fy:-80},
          {id:'core-design', name: 'Design' , fx: 15, fy:-40},
          {id:'core-implementation', name: 'Implementation', fx: 15, fy: 0},
          {id:'core-verification', name: 'Verification', fx: 15, fy: 40},
          {id:'core-gap-evaluation', name: 'Policy gap evaluation', fx: 15, fy: 80},
          {id:'core-metrics', name: 'Metrics', fx: -15, fy: 100},
          {id:'core-training/education', name: 'Training/Education' , fx: -15, fy: 60},
          {id:'core-culture', name: 'Culture' , fx: -15, y: 20},
          {id:'core-operation', name: 'Operation', fx: -15, y: -20},
          {id: 'skf', name: 'SKF'},
          {id: 'asvs', name: 'ASVS'},
          {id: 'wstg', name: 'WSTG'},
          {id: 'zap', name: 'ZAP'}
         ],
         links: [
          { source: 'core-requirements', target: 'core-design'},
          { source: 'core-design', target: 'core-implementation'},
          { source: 'core-implementation', target: 'core-verification'},
          { source: 'core-verification', target: 'core-gap-evaluation'},
          { source: 'core-verification', target: 'core-metrics'},
          { source: 'core-metrics', target: 'core-training/education'},
          { source: 'core-metrics', target: 'core-gap-evaluation'},
          { source: 'core-training/education', target: 'core-culture'},
          { source: 'core-culture', target: 'core-operation'},
          { source: 'core-operation', target: 'core-requirements', name: 'iterate'},
          { source: 'core-requirements', target: 'skf',},
          { source: 'core-requirements', target: 'asvs',},
          { source: 'core-implementation', target: 'wstg', name: 'guide'},
          { source: 'core-implementation', target: 'zap', name: 'tool' },
         ],
       });
  const [ignoreTypes, setIgnoreTypes] = useState(['same']);
  const [maxCount, setMaxCount] = useState(0);
  const [maxNodeSize, setMaxNodeSize] = useState(0);
  const { dataLoading, dataTree, getStoreKey, dataStore } = useDataStore();
  // useEffect(() => {
  //   const gData: any = {
  //     nodes: [],
  //     links: [],
  //   };

    // const populateGraphData = (node) => {
    //   let filteredLinks = [];
    //   if (node.links) {
    //     filteredLinks = node.links.filter((x) => x.document && !ignoreTypes.includes(x.ltype.toLowerCase()));
    //   }
    //   filteredLinks.forEach((x: LinkedTreeDocument) => {
    //     gData.links.push({
    //       source: getStoreKey(node),
    //       target: getStoreKey(x.document),
    //       count: x.ltype === 'Contains' ? 2 : 1,
    //       type: x.ltype,
    //     });
    //     populateGraphData(x.document);
    //   });
    // };
    // dataTree.forEach((x) => populateGraphData(x));

  //   const nodesMap = {};
  //   const addNode = function (name) {
  //     if (!nodesMap[name]) {
  //       const storedDoc = dataStore[name];
  //       nodesMap[name] = {
  //         id: name,
  //         size: 1,
  //         name: storedDoc ? storedDoc.displayName : name,
  //         doctype: storedDoc ? storedDoc.doctype : 'Unknown',
  //       };
  //       gData.nodes.push(nodesMap[name]);
  //     } else {
  //       nodesMap[name].size += 1;
  //     }
  //   };
  //   gData.links.forEach((link) => {
  //     addNode(link.source);
  //     addNode(link.target);
  //   });

  //   setMaxNodeSize(gData.nodes.map((n) => n.size).reduce((a, b) => Math.max(a, b)));
  //   setMaxCount(gData.links.map((l) => l.count).reduce((a, b) => Math.max(a, b)));

  //   gData.links = gData.links.map((l) => {
  //     return { source: l.target, target: l.source, count: l.count, type: l.type };
  //   });
  //   setGraphData(gData);
  // }, [ignoreTypes]);

  const getLinkColor = (ltype) => {
    switch (ltype.toLowerCase()) {
      case 'related':
        return 'skyblue';
      case 'linked to':
        return 'gray';
      case 'same':
        return 'red';
      default:
        return 'white';
    }
  };

  const getNodeColor = (id) => {
    if(id.startsWith('core-'))
    {
      return ''
    }
    return 'gray'
  };

  const toggleLinks = (name) => {
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

  return (
    <div>
      <LoadingAndErrorIndicator loading={dataLoading} error={null} />

      <Checkbox
        label="Contains"
        checked={!ignoreTypes.includes('contains')}
        onChange={() => toggleLinks('contains')}
      />
      {' | '}
      <Checkbox
        label="Related"
        checked={!ignoreTypes.includes('related')}
        onChange={() => toggleLinks('related')}
      />
      {' | '}
      <Checkbox
        label="Linked To"
        checked={!ignoreTypes.includes('linked to')}
        onChange={() => toggleLinks('linked to')}
      />
      {' | '}
      <Checkbox label="Same" checked={!ignoreTypes.includes('same')} onChange={() => toggleLinks('same')} />

      {graphData && (
        <ForceGraph2D
          graphData={graphData}
          nodeRelSize={10}
          nodeVal={(n) => 1}
          nodeLabel={(n) => n.name}
          nodeColor={(n: any) => getNodeColor(n.id)} 
          // linkOpacity={0.5}
          linkLabel={(n) => n.name}
          linkWidth={(d) => 4}
          linkDirectionalArrowLength={5}
          linkDirectionalArrowRelPos={1}
          nodeCanvasObjectMode={() => 'after'}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const fontSize = 8 / globalScale;
            ctx.font = `${fontSize}px Sans-Serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = 'white'; //node.color;
            ctx.fillText(node.name, node.x, node.y);
          }}
          linkCanvasObjectMode={() => 'after'}
          linkCanvasObject={(link, ctx, globalScale) => {
            const MAX_FONT_SIZE = 6;
          const LABEL_NODE_MARGIN = globalScale * 1.5;

          const start = link.source;
          const end = link.target;

          // ignore unbound links
          if (typeof start !== 'object' || typeof end !== 'object' || !link.name) return;

          // calculate label positioning
          const textPos = Object.assign(...['x', 'y'].map(c => ({
            [c]: start[c] + (end[c] - start[c]) / 2 // calc middle point
          })));

          const relLink = { x: end.x - start.x, y: end.y - start.y };

          const maxTextLength = Math.sqrt(Math.pow(relLink.x, 2) + Math.pow(relLink.y, 2)) - LABEL_NODE_MARGIN * 2;

          let textAngle = Math.atan2(relLink.y, relLink.x);
          // maintain label vertical orientation for legibility
          if (textAngle > Math.PI / 2) textAngle = -(Math.PI - textAngle);
          if (textAngle < -Math.PI / 2) textAngle = -(-Math.PI - textAngle);

          const label = link.name;

          // estimate fontSize to fit in link length
          ctx.font = '1px Sans-Serif';
          const fontSize = Math.min(MAX_FONT_SIZE, maxTextLength / ctx.measureText(label).width);
          ctx.font = `${fontSize}px Sans-Serif`;
          const textWidth = ctx.measureText(label).width;
          const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.2); // some padding

          // draw text label (with background rect)
          ctx.save();
          ctx.translate(textPos.x, textPos.y);
          ctx.rotate(textAngle);

          ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
          ctx.fillRect(- bckgDimensions[0] / 2, - bckgDimensions[1] / 2, ...bckgDimensions);

          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillStyle = 'darkgrey';
          ctx.fillText(label, 0, 0);
          ctx.restore();
          }}
        />
      )}
    </div>
  );
};
