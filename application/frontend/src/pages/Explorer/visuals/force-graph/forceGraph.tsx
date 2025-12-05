import { LoadingAndErrorIndicator } from 'application/frontend/src/components/LoadingAndErrorIndicator';
import { useEnvironment } from 'application/frontend/src/hooks';
import { useDataStore } from 'application/frontend/src/providers/DataProvider';
import { LinkedTreeDocument } from 'application/frontend/src/types';
import axios from 'axios';
import React, { useEffect, useState } from 'react';
import ForceGraph3D from 'react-force-graph-3d';


//import { Checkbox, Dropdown, Form } from 'semantic-ui-react';

// For types of dropdown options
interface DropdownOption {
  key: string;
  text: string;
  value: string;
  disabled?: boolean;
}

export const ExplorerForceGraph = () => {
  const [graphData, setGraphData] = useState();
  const [ignoreTypes, setIgnoreTypes] = useState(['same']);
  const [maxCount, setMaxCount] = useState(0);
  const [maxNodeSize, setMaxNodeSize] = useState(0);
  const { dataLoading, dataTree, getStoreKey, dataStore } = useDataStore();

  const [filterTypeA, setFilterTypeA] = useState('');
  const [filterTypeB, setFilterTypeB] = useState('');

  const [creOptions, setCreOptions] = useState<DropdownOption[]>([]);
  const [combinedOptions, setCombinedOptions] = useState<DropdownOption[]>([]);

  const [showAll, setShowAll] = useState(true);

  const getBaseName = (standardId: string): string => {
    return standardId.split(':')[0];
  };

  const getGroupedStandardId = (baseName: string): string => {
    return `grouped_${baseName}`;
  };

  const getBaseNameFromGrouped = (groupedId: string): string => {
    return groupedId.replace('grouped_', '');
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
    const gData: any = {
      nodes: [],
      links: [],
    };

    const allNodes = Object.values(dataStore);

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
      groupedStandards.get(baseName)!.push(node);
    });

    const originalToGroupedMap = new Map<string, string>();
    groupedStandards.forEach((nodes, baseName) => {
      const groupedId = getGroupedStandardId(baseName);
      nodes.forEach((node) => {
        originalToGroupedMap.set(node.id, groupedId);
      });
    });

    const standardNodeIds = allStandardNodes.map((node: any) => node.id);
    console.log('Standard IDs from JSON data:', standardNodeIds);
    console.log('Grouped standards:', Array.from(groupedStandards.keys()));

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
        return node.doctype?.toLowerCase() === type.toLowerCase();
      }

      if (isGroupedStandard(filterVal)) {
        const baseName = getBaseNameFromGrouped(filterVal);
        return node.doctype?.toLowerCase() === 'standard' && getBaseName(node.id) === baseName;
      }

      return node.id === filterVal;
    };



    // OLD APPROACH: Complex filtering during graph traversal with many nested conditions
    // This made the code hard to understand and debug
    // let filteredLinks = [];
    // if (node.links) {
    //   filteredLinks = node.links.filter((x) => {
    //     if (!x.document || ignoreTypes.includes(x.ltype.toLowerCase())) return false;
    //     if (!filterTypeA && !filterTypeB) return true; // No filter, show all

    //     const sourceNode = node;
    //     const targetNode = x.document;

    //     if (filterTypeA && filterTypeB) {
    //       // Check if we have a specific CRE selected (not "all_cre")
    //       const isSpecificCRE = filterTypeA && !filterTypeA.startsWith('all_');
    //       // Check if we have a specific Standard selected (not "all_standard")
    //       const isSpecificStandard = filterTypeB && !filterTypeB.startsWith('all_');

    //       if (isSpecificCRE && isSpecificStandard) {
    //         // Handle grouped standards in filtering
    //         if (isGroupedStandard(filterTypeA) || isGroupedStandard(filterTypeB)) {
    //           return (
    //             (matchesFilter(sourceNode, filterTypeA) && matchesFilter(targetNode, filterTypeB)) ||
    //             (matchesFilter(sourceNode, filterTypeB) && matchesFilter(targetNode, filterTypeA))
    //           );
    //         }
    //         // Show only direct relationships between the specific CRE and specific Standard
    //         return (
    //           (sourceNode.id === filterTypeA && targetNode.id === filterTypeB) ||
    //           (sourceNode.id === filterTypeB && targetNode.id === filterTypeA)
    //         );
    //       }

    //       // If either filter is "ALL" type, use the original logic
    //       return (
    //         (matchesFilter(sourceNode, filterTypeA) && matchesFilter(targetNode, filterTypeB)) ||
    //         (matchesFilter(sourceNode, filterTypeB) && matchesFilter(targetNode, filterTypeA))
    //       );
    //     }

    //     // Single filter logic remains the same
    //     if (filterTypeA && !filterTypeB) {
    //       return matchesFilter(sourceNode, filterTypeA) || matchesFilter(targetNode, filterTypeA);
    //     }

    //     if (!filterTypeA && filterTypeB) {
    //       return matchesFilter(sourceNode, filterTypeB) || matchesFilter(targetNode, filterTypeB);
    //     }

    //     return true;
    //   });
    // }


    const populateGraphData = (node: any) => {
      if (node.links && Array.isArray(node.links)) {
        node.links.forEach((x: LinkedTreeDocument) => {
          if (x.document && !ignoreTypes.includes(x.ltype.toLowerCase())) {
            const sourceKey =
              node.doctype?.toLowerCase() === 'standard'
                ? originalToGroupedMap.get(node.id) || getStoreKey(node)
                : getStoreKey(node);
            const targetKey =
              x.document.doctype?.toLowerCase() === 'standard'
                ? originalToGroupedMap.get(x.document.id) || getStoreKey(x.document)
                : getStoreKey(x.document);

            gData.links.push({
              source: sourceKey,
              target: targetKey,
              count: x.ltype === 'Contains' ? 2 : 1,
              type: x.ltype,
            });

            populateGraphData(x.document);
          }
        });
      }
    };

    dataTree.forEach((x) => populateGraphData(x));

    if (!showAll && (filterTypeA || filterTypeB)) {
      gData.links = gData.links.filter((link: any) => {
        let sourceNode = dataStore[link.source];
        let targetNode = dataStore[link.target];

        if (link.source.startsWith('grouped_')) {
          const baseName = getBaseNameFromGrouped(link.source);
          sourceNode = {
            id: link.source,
            doctype: 'standard',
            displayName: baseName,
            links: [],
            url: '',
            name: baseName,
          };
        }

        if (link.target.startsWith('grouped_')) {
          const baseName = getBaseNameFromGrouped(link.target);
          targetNode = {
            id: link.target,
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

    const nodesMap: any = {};
    const addNode = function (name: string) {
      if (!nodesMap[name]) {
        if (name.startsWith('grouped_')) {
          const baseName = getBaseNameFromGrouped(name);
          const groupedNodes = groupedStandards.get(baseName) || [];
          const totalSize = groupedNodes.length;

          nodesMap[name] = {
            id: name,
            size: totalSize,
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

    gData.links.forEach((link: any) => {
      addNode(link.source);
      addNode(link.target);
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

    setMaxNodeSize(gData.nodes.map((n: any) => n.size).reduce((a: number, b: number) => Math.max(a, b), 0));
    setMaxCount(gData.links.map((l: any) => l.count).reduce((a: number, b: number) => Math.max(a, b), 0));

    gData.links = gData.links.map((l: any) => {
      return { source: l.target, target: l.source, count: l.count, type: l.type };
    });

    setGraphData(gData);
  }, [ignoreTypes, dataTree, filterTypeA, filterTypeB, showAll, dataStore]);

  const getLinkColor = (ltype: string) => {
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

  const getNodeColor = (doctype: string) => {
    switch (doctype.toLowerCase()) {
      case 'cre':
        return 'lightblue';
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

  return (
    <div style={{ margin: 0 }}>
      <LoadingAndErrorIndicator loading={dataLoading} error={null} />

      <div style={{ marginBottom: '10px', padding: '10px' }}>
        <label className="inline-flex items-center mr-4 cursor-pointer">
          <input
            type="checkbox"
            checked={!ignoreTypes.includes('contains')}
            onChange={() => toggleLinks('contains')}
            className="mr-2"
          />
          <span>Contains</span>
        </label>
        <span className="mx-2">|</span>
        <label className="inline-flex items-center mr-4 cursor-pointer">
          <input
            type="checkbox"
            checked={!ignoreTypes.includes('related')}
            onChange={() => toggleLinks('related')}
            className="mr-2"
          />
          <span>Related</span>
        </label>
        <span className="mx-2">|</span>
        <label className="inline-flex items-center mr-4 cursor-pointer">
          <input
            type="checkbox"
            checked={!ignoreTypes.includes('linked to')}
            onChange={() => toggleLinks('linked to')}
            className="mr-2"
          />
          <span>Linked To</span>
        </label>
        <span className="mx-2">|</span>
        <label className="inline-flex items-center mr-4 cursor-pointer">
          <input
            type="checkbox"
            checked={!ignoreTypes.includes('same')}
            onChange={() => toggleLinks('same')}
            className="mr-2"
          />
          <span>Same</span>
        </label>
      </div>

      <div style={{ marginBottom: '10px', marginTop: '10px', marginLeft: '10px' }}>
        <select
          value={filterTypeA}
          onChange={(e) => setFilterTypeA(e.target.value)}
          className="border border-gray-300 rounded px-3 py-2 mr-2"
          style={{ marginRight: '10px' }}
        >
          {creOptions.map((opt) => (
            <option key={opt.key} value={opt.value} disabled={opt.disabled}>
              {opt.text}
            </option>
          ))}
        </select>
        <select
          value={filterTypeB}
          onChange={(e) => setFilterTypeB(e.target.value)}
          className="border border-gray-300 rounded px-3 py-2"
        >
          {combinedOptions.map((opt) => (
            <option key={opt.key} value={opt.value} disabled={opt.disabled}>
              {opt.text}
            </option>
          ))}
        </select>
        <span className="mx-2">|</span>
        <label className="inline-flex items-center cursor-pointer">
          <input
            type="checkbox"
            checked={showAll}
            onChange={() => setShowAll(!showAll)}
            className="mr-2"
          />
          <span>Show All</span>
        </label>
      </div>
      {showAll || filterTypeA || filterTypeB ? (
        graphData && (
          <ForceGraph3D
            graphData={graphData}
            nodeRelSize={8}
            nodeVal={(n: any) => Math.max((20 * n.size) / maxNodeSize, 0.001)}
            nodeLabel={(n: any) => n.name + ' (' + n.size + ')'}
            nodeColor={(n: any) => getNodeColor(n.doctype)}
            linkOpacity={0.5}
            linkColor={(l: any) => getLinkColor(l.type)}
            linkWidth={() => 4}
          />
        )
      ) : (
        <div style={{ marginTop: '20px', color: 'gray', marginLeft: '10px' }}>
          Please select at least one filter to view the graph or check "Show All".
        </div>
      )}
    </div>
  );
};
