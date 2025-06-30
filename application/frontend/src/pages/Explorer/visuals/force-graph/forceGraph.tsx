import './forceGraph.scss';

import { LoadingAndErrorIndicator } from 'application/frontend/src/components/LoadingAndErrorIndicator';
import { useEnvironment } from 'application/frontend/src/hooks';
import { useDataStore } from 'application/frontend/src/providers/DataProvider';
import { LinkedTreeDocument } from 'application/frontend/src/types';
import axios from 'axios';
import React, { useEffect, useState } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import { Checkbox, Dropdown, Form } from 'semantic-ui-react';

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

  // ADDING STATE FOR FILTERING LOGIC
  const [filterTypeA, setFilterTypeA] = useState('');
  const [filterTypeB, setFilterTypeB] = useState('');

  // Separated CRE options and combined options with proper typing
  const [creOptions, setCreOptions] = useState<DropdownOption[]>([]);
  const [combinedOptions, setCombinedOptions] = useState<DropdownOption[]>([]);

  // Adding a show all checkbox
  const [showAll, setShowAll] = useState(true);

  // Helper function to get base name from standard ID
  const getBaseName = (standardId: string): string => {
    // Split by ':' and take the first part
    return standardId.split(':')[0];
  };

  // Helper function to create grouped standard ID
  const getGroupedStandardId = (baseName: string): string => {
    return `grouped_${baseName}`;
  };

  //Added helper function for cleaner code organization
  const getBaseNameFromGrouped = (groupedId: string): string => {
    return groupedId.replace('grouped_', '');
  };

  // Build CRE options separately for better organization and type safety from Data Store
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

    // Get all the nodes and types
    const allNodes = Object.values(dataStore);

    // Function to collect standards from tree structure
    function collectStandards(node: any, standards: any[] = []): any[] {
      // Added optional chaining for better null safety
      if (node.doctype && node.doctype.toLowerCase() === 'standard') {
        standards.push(node);
      }
      //Added Array.isArray check for better safety
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

    // Group standards by base name
    const groupedStandards = new Map<string, any[]>();
    allStandardNodes.forEach((node: any) => {
      const baseName = getBaseName(node.id);
      if (!groupedStandards.has(baseName)) {
        groupedStandards.set(baseName, []);
      }
      groupedStandards.get(baseName)!.push(node);
    });

    // Create mapping for original IDs to grouped IDs
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

    // Build standard dropdown options with count display for better Ui
    const standardDropdownOptions: DropdownOption[] = Array.from(groupedStandards.entries()).map(
      ([baseName, group]) => ({
        key: getGroupedStandardId(baseName),
        text: `${baseName} (${group.length})`,
        value: getGroupedStandardId(baseName),
      })
    );

    // Helper functions for filtering logic
    const isAll = (val: string) => val && val.startsWith('all_');
    const isGroupedStandard = (val: string) => val && val.startsWith('grouped_');
    const getTypeFromAll = (val: string) => val.replace('all_', '');

    // Improved matchesFilter function with better null safety and type checking
    const matchesFilter = (node: any, filterVal: string): boolean => {
      if (!filterVal || filterVal === '') return true; // No filter, show all

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

    // NEW APPROACH: Simplified graph data population - collect all data first, then filter
    // This is cleaner and easier to debug than filtering during traversal
    const populateGraphData = (node: any) => {
      if (node.links && Array.isArray(node.links)) {
        node.links.forEach((x: LinkedTreeDocument) => {
          if (x.document && !ignoreTypes.includes(x.ltype.toLowerCase())) {
            // Use grouped IDs for standard nodes in links
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

    // Build the complete graph first
    dataTree.forEach((x) => populateGraphData(x));

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

    // NEW APPROACH: Apply filtering after building complete graph for better separation of concerns
    if (!showAll && (filterTypeA || filterTypeB)) {
      gData.links = gData.links.filter((link: any) => {
        // Get source and target nodes with better error handling
        let sourceNode = dataStore[link.source];
        let targetNode = dataStore[link.target];

        // NEW APPROACH: Better handling of grouped standard nodes with all required properties
        if (link.source.startsWith('grouped_')) {
          const baseName = getBaseNameFromGrouped(link.source);
          sourceNode = {
            id: link.source,
            doctype: 'standard',
            displayName: baseName,
            links: [],
            url: '', // Add missing properties for type safety
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
            url: '', // Add missing properties for type safety
            name: baseName,
          };
        }

        if (!sourceNode || !targetNode) return false;

        // NEW APPROACH: Simplified filtering - show link if any node matches any filter
        // This is more permissive and user-friendly than the complex logic above
        const sourceMatchesA = matchesFilter(sourceNode, filterTypeA);
        const sourceMatchesB = matchesFilter(sourceNode, filterTypeB);
        const targetMatchesA = matchesFilter(targetNode, filterTypeA);
        const targetMatchesB = matchesFilter(targetNode, filterTypeB);

        return sourceMatchesA || sourceMatchesB || targetMatchesA || targetMatchesB;
      });
    }

    // Build nodes from filtered links
    const nodesMap: any = {};
    const addNode = function (name: string) {
      if (!nodesMap[name]) {
        // Check if this is a grouped standard node
        if (name.startsWith('grouped_')) {
          const baseName = getBaseNameFromGrouped(name);
          const groupedNodes = groupedStandards.get(baseName) || [];
          const totalSize = groupedNodes.length;

          nodesMap[name] = {
            id: name,
            size: totalSize,
            name: baseName,
            doctype: 'standard',
            originalNodes: groupedNodes, // Store original nodes for reference
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

    // Clean, organized combined options with clear sections and separators
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

    // Added initial value to reduce array - with better error handling
    setMaxNodeSize(gData.nodes.map((n: any) => n.size).reduce((a: number, b: number) => Math.max(a, b), 0));
    setMaxCount(gData.links.map((l: any) => l.count).reduce((a: number, b: number) => Math.max(a, b), 0));

    // Reverse links for proper display
    gData.links = gData.links.map((l: any) => {
      return { source: l.target, target: l.source, count: l.count, type: l.type };
    });

    setGraphData(gData);
  }, [ignoreTypes, dataTree, filterTypeA, filterTypeB, showAll, dataStore]); // NEW APPROACH: Removed standardOptions dependency

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
        // OLD APPROACH: CRE nodes had no color (empty string) which made them hard to see
        // return '';
        // NEW APPROACH: Give CRE nodes a visible color for better UI
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

      <div style={{ marginBottom: '10px', marginTop: '10px', marginLeft: '10px' }}>
        <Dropdown
          placeholder="Select CRE"
          options={creOptions}
          value={filterTypeA}
          onChange={(e, data) => setFilterTypeA((data.value ?? '') as string)}
          style={{ marginRight: '10px' }}
          selection
          search
        />
        <Dropdown
          placeholder="Select Standard or CRE"
          options={combinedOptions}
          value={filterTypeB}
          onChange={(e, data) => setFilterTypeB((data.value ?? '') as string)}
          selection
          search
        />
        {' | '}
        <Checkbox label="Show All" checked={showAll} onChange={() => setShowAll(!showAll)} />
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
        <div style={{ marginTop: '20px', color: 'gray' }}>
          Please select at least one filter to view the graph or check "Show All".
        </div>
      )}
    </div>
  );
};
