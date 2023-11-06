import './forceGraph.scss';

import { LoadingAndErrorIndicator } from 'application/frontend/src/components/LoadingAndErrorIndicator';
import { useDataStore } from 'application/frontend/src/providers/DataProvider';
import { LinkedTreeDocument } from 'application/frontend/src/types';
import React, { useEffect, useState } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import { Checkbox, Form } from 'semantic-ui-react';

export const ExplorerForceGraph = () => {
  const [graphData, setGraphData] = useState();
  const [ignoreTypes, setIgnoreTypes] = useState(['same']);
  const [maxCount, setMaxCount] = useState(0);
  const [maxNodeSize, setMaxNodeSize] = useState(0);
  const { dataLoading, dataTree, getStoreKey, dataStore } = useDataStore();
  useEffect(() => {
    const gData: any = {
      nodes: [],
      links: [],
    };

    const populateGraphData = (node) => {
      let filteredLinks = [];
      if (node.links) {
        filteredLinks = node.links.filter((x) => x.document && !ignoreTypes.includes(x.ltype.toLowerCase()));
      }
      filteredLinks.forEach((x: LinkedTreeDocument) => {
        gData.links.push({
          source: getStoreKey(node),
          target: getStoreKey(x.document),
          count: x.ltype === 'Contains' ? 2 : 1,
          type: x.ltype,
        });
        populateGraphData(x.document);
      });
    };
    dataTree.forEach((x) => populateGraphData(x));

    const nodesMap = {};
    const addNode = function (name) {
      if (!nodesMap[name]) {
        const storedDoc = dataStore[name];
        nodesMap[name] = {
          id: name,
          size: 1,
          name: storedDoc ? storedDoc.displayName : name,
          doctype: storedDoc ? storedDoc.doctype : 'Unknown',
        };
        gData.nodes.push(nodesMap[name]);
      } else {
        nodesMap[name].size += 1;
      }
    };
    gData.links.forEach((link) => {
      addNode(link.source);
      addNode(link.target);
    });

    setMaxNodeSize(gData.nodes.map((n) => n.size).reduce((a, b) => Math.max(a, b)));
    setMaxCount(gData.links.map((l) => l.count).reduce((a, b) => Math.max(a, b)));

    gData.links = gData.links.map((l) => {
      return { source: l.target, target: l.source, count: l.count, type: l.type };
    });
    setGraphData(gData);
  }, [ignoreTypes]);

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

  const getNodeColor = (doctype) => {
    switch (doctype.toLowerCase()) {
      case 'cre':
        return '';
      case 'standard':
        return 'orange';
      case 'tool':
        return 'lightgreen';
      case 'linked to':
        return 'red';
      default:
        return 'purple';
    }
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
        <ForceGraph3D
          graphData={graphData}
          nodeRelSize={8}
          nodeVal={(n) => Math.max((20 * n.size) / maxNodeSize, 0.001)}
          nodeLabel={(n) => n.name + ' (' + n.size + ')'}
          nodeColor={(n: any) => getNodeColor(n.doctype)}
          linkOpacity={0.5}
          linkColor={(l) => getLinkColor(l.type)}
          linkWidth={(d) => 4}
        />
      )}
    </div>
  );
};
