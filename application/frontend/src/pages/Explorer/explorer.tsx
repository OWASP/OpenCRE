import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { TYPE_CONTAINS, TYPE_LINKED_TO } from '../../const';
import { useDataStore } from '../../providers/DataProvider';
import { LinkedTreeDocument, TreeDocument } from '../../types';
import { getDocumentDisplayName } from '../../utils';
import { getInternalUrl } from '../../utils/document';
import { LinkedStandards } from './LinkedStandards';




export const Explorer = () => {
  const { dataLoading, dataTree } = useDataStore();
  const [loading, setLoading] = useState<boolean>(false);
  const [filter, setFilter] = useState('');
  const [filteredTree, setFilteredTree] = useState<TreeDocument[]>();
  const applyHighlight = (text, term) => {
    if (!term) return text;
    let index = text.toLowerCase().indexOf(term);
    if (index >= 0) {
      return (
        <>
          {text.substring(0, index)}
          <span style={{ backgroundColor: 'yellow' }}>{text.substring(index, index + term.length)}</span>
          {text.substring(index + term.length)}
        </>
      );
    }
    return text;
  };

  const filterFunc = (doc: TreeDocument, term: string) =>
    doc?.displayName?.toLowerCase().includes(term) || doc?.name?.toLowerCase().includes(term);

  const recursiveFilter = (doc: TreeDocument, term: string) => {
    if (doc.links) {
      const filteredLinks: LinkedTreeDocument[] = [];
      doc.links.forEach((x) => {
        const filteredDoc = recursiveFilter(x.document, term);
        if (filterFunc(x.document, term) || filteredDoc) {
          filteredLinks.push({ ltype: x.ltype, document: filteredDoc || x.document });
        }
      });
      doc.links = filteredLinks;
    }

    if (filterFunc(doc, term) || doc.links?.length) {
      return doc;
    }
    return null;
  };

  const [collapsedItems, setCollapsedItems] = useState<string[]>([]);
  const isCollapsed = (id: string) => collapsedItems.includes(id);
  const toggleItem = (id: string) => {
    if (collapsedItems.includes(id)) {
      setCollapsedItems(collapsedItems.filter((itemId) => itemId !== id));
    } else {
      setCollapsedItems([...collapsedItems, id]);
    }
  };

  useEffect(() => {
    if (dataTree.length) {
      const treeCopy = structuredClone(dataTree);
      const filTree: TreeDocument[] = [];
      treeCopy
        .map((x) => recursiveFilter(x, filter))
        .forEach((x) => {
          if (x) {
            filTree.push(x);
          }
        });
      setFilteredTree(filTree);
    }
  }, [filter, dataTree, setFilteredTree]);

  useEffect(() => {
    setLoading(dataLoading);
  }, [dataLoading]);

  function processNode(item, depth = 0) {
    if (!item) {
      return <></>;
    }
    item.displayName = item.displayName ?? getDocumentDisplayName(item);
    item.url = item.url ?? getInternalUrl(item);
    item.links = item.links ?? [];

    const contains = item.links.filter((x) => x.ltype === TYPE_CONTAINS);
    const linkedTo = item.links.filter((x) => x.ltype === TYPE_LINKED_TO);

    const creCode = item.id;
    const creName = item.displayName.split(' : ').pop();

    return (
      <li
        key={item.id || Math.random()}
        style={{
          listStyle: 'none',
          marginLeft: depth > 0 ? '40px' : '0',
          paddingLeft: '8px',
          borderLeft: depth > 0 ? '4px solid #ddd' : 'none',
          marginTop: '4px',
          marginBottom: '4px',
          backgroundColor: depth % 2 === 0 ? '#f9f9f9' : '#ffffff'
        }}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', padding: '4px 0' }}>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            {contains.length > 0 && (
              <span
                onClick={() => toggleItem(item.id)}
                style={{
                  cursor: 'pointer',
                  display: 'inline-block',
                  width: '0',
                  height: '0',
                  marginRight: '8px',
                  borderTop: isCollapsed(item.id) ? '6px solid transparent' : '6px solid #333',
                  borderBottom: isCollapsed(item.id) ? '6px solid transparent' : '0',
                  borderLeft: isCollapsed(item.id) ? '6px solid #333' : '6px solid transparent',
                  borderRight: isCollapsed(item.id) ? '0' : '6px solid transparent',
                  transition: 'all 0.2s'
                }}
              />
            )}
            <Link
              to={item.url}
              style={{
                fontSize: '16px',
                fontWeight: 'normal',
                textDecoration: 'none',
                color: '#0066cc'
              }}
            >
              <span style={{ color: '#666', marginRight: '4px' }}>{applyHighlight(creCode, filter)}:</span>
              <span style={{ color: '#0066cc' }}>{applyHighlight(creName, filter)}</span>
            </Link>
          </div>
          <LinkedStandards
            linkedTo={linkedTo}
            applyHighlight={applyHighlight}
            creCode={creCode}
            filter={filter}
          />
        </div>
        {contains.length > 0 && !isCollapsed(item.id) && (
          <ul style={{ padding: 0, margin: 0 }}>
            {contains.map((child) => processNode(child.document, depth + 1))}
          </ul>
        )}
      </li>
    );
  }

  function update(event) {
    setFilter(event.target.value.toLowerCase());
  }

  return (
    <>
      <main
        id="explorer-content"
        style={{
          padding: '30px',
          marginTop: 'var(--header-height)',
          marginBottom: 0,
          fontFamily: 'Arial, sans-serif'
        }}
      >
        <h1 style={{ fontSize: '28px', fontWeight: 'bold', marginBottom: '10px' }}>Open CRE Explorer</h1>
        <p style={{ marginBottom: '20px', color: '#333' }}>
          A visual explorer of Open Common Requirement Enumerations (CREs). Originally created by:{' '}
          <a
            target="_blank"
            href="https://zeljkoobrenovic.github.io/opencre-explorer/"
            style={{ color: '#0066cc', textDecoration: 'none' }}
          >
            Zeljko Obrenovic
          </a>
          .
        </p>

        <div id="explorer-wrapper">
          <div style={{ marginBottom: '15px' }}>
            <input
              id="filter"
              type="text"
              placeholder="Search Explorer..."
              onKeyUp={update}
              style={{
                fontSize: '16px',
                height: '32px',
                width: '320px',
                marginBottom: '10px',
                borderRadius: '3px',
                border: '1px solid #ccc',
                padding: '0 8px'
              }}
            />
            <div id="search-summary"></div>
          </div>
          <div
            id="graphs-menu"
            style={{
              display: 'flex',
              marginBottom: '20px',
              flexWrap: 'wrap'
            }}
          >
            <span style={{ marginRight: '10px', fontWeight: 'bold' }}>Explore visually:</span>
            <a
              href="/explorer/force_graph"
              style={{ color: '#0066cc', textDecoration: 'none', marginRight: '15px' }}
            >
              Dependency Graph
            </a>
            <span style={{ marginRight: '10px', color: '#ccc' }}>|</span>
            <a
              href="/explorer/circles"
              style={{ color: '#0066cc', textDecoration: 'none' }}
            >
              Zoomable circles
            </a>
          </div>
        </div>
        <LoadingAndErrorIndicator loading={loading} error={null} />
        <ul style={{ padding: 0, margin: 0, listStyle: 'none' }}>
          {filteredTree?.map((item) => {
            return processNode(item, 0);
          })}
        </ul>
      </main>
    </>
  );
};








// import React, { useEffect, useState } from 'react';
// import { Link } from 'react-router-dom';

// import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
// import { TYPE_CONTAINS, TYPE_LINKED_TO } from '../../const';
// import { useDataStore } from '../../providers/DataProvider';
// import { LinkedTreeDocument, TreeDocument } from '../../types';
// import { getDocumentDisplayName } from '../../utils';
// import { getInternalUrl } from '../../utils/document';
// import { LinkedStandards } from './LinkedStandards';

// export const Explorer = () => {
//   const { dataLoading, dataTree } = useDataStore();
//   const [loading, setLoading] = useState<boolean>(false);
//   const [filter, setFilter] = useState('');
//   const [filteredTree, setFilteredTree] = useState<TreeDocument[]>();

//   const applyHighlight = (text: string, term: string | undefined) => {
//     if (!term) return text;
//     const lower = text?.toLowerCase() ?? '';
//     const idx = lower.indexOf(term);
//     if (idx >= 0) {
//       return (
//         <>
//           {text.substring(0, idx)}
//           <span className="bg-yellow-200">{text.substring(idx, idx + term.length)}</span>
//           {text.substring(idx + term.length)}
//         </>
//       );
//     }
//     return text;
//   };

//   const filterFunc = (doc: TreeDocument, term: string) =>
//     doc?.displayName?.toLowerCase().includes(term) || doc?.name?.toLowerCase().includes(term);

//   const recursiveFilter = (doc: TreeDocument, term: string) => {
//     if (!doc) return null;
//     if (doc.links) {
//       const filteredLinks: LinkedTreeDocument[] = [];
//       doc.links.forEach((x) => {
//         const filteredDoc = recursiveFilter(x.document, term);
//         if (filterFunc(x.document, term) || filteredDoc) {
//           filteredLinks.push({ ltype: x.ltype, document: (filteredDoc as TreeDocument) || x.document });
//         }
//       });
//       doc = { ...doc, links: filteredLinks };
//     }

//     if (filterFunc(doc, term) || doc.links?.length) {
//       return doc;
//     }
//     return null;
//   };

//   const [collapsedItems, setCollapsedItems] = useState<string[]>([]);
//   const isCollapsed = (id: string) => collapsedItems.includes(id);
//   const toggleItem = (id: string) => {
//     if (collapsedItems.includes(id)) {
//       setCollapsedItems(collapsedItems.filter((itemId) => itemId !== id));
//     } else {
//       setCollapsedItems([...collapsedItems, id]);
//     }
//   };

//   useEffect(() => {
//     if (dataTree.length) {
//       const treeCopy = structuredClone(dataTree);
//       const filTree: TreeDocument[] = [];
//       treeCopy
//         .map((x: TreeDocument) => recursiveFilter(x, filter))
//         .forEach((x: TreeDocument | null) => {
//           if (x) {
//             filTree.push(x);
//           }
//         });
//       setFilteredTree(filTree);
//     } else {
//       setFilteredTree([]);
//     }
//   }, [filter, dataTree, setFilteredTree]);

//   useEffect(() => {
//     setLoading(dataLoading);
//   }, [dataLoading]);

//   function processNode(item: TreeDocument | null) {
//     if (!item) {
//       return <></>;
//     }

//     item.displayName = item.displayName ?? getDocumentDisplayName(item);
//     item.url = item.url ?? getInternalUrl(item);
//     item.links = item.links ?? [];

//     const contains = item.links.filter((x) => x.ltype === TYPE_CONTAINS);
//     const linkedTo = item.links.filter((x) => x.ltype === TYPE_LINKED_TO);

//     const creCode = item.id;
//     const creName = item.displayName.split(' : ').pop();

//     return (
//       <li
//         key={Math.random()}
//         className="border-t border-dotted border-gray-300 ml-10 mb-2 bg-gray-50/20 rounded-sm"
//       >
//         <div className="pl-3 py-3">
//           <div className="flex items-start gap-3">
//             {contains.length > 0 && (
//               <button
//                 onClick={() => toggleItem(item.id)}
//                 aria-expanded={!isCollapsed(item.id)}
//                 className={`flex items-center justify-center w-6 h-6 transition-transform ${isCollapsed(item.id) ? 'rotate-0' : 'rotate-90'
//                   }`}
//                 title="Toggle children"
//               >
//                 <svg
//                   xmlns="http://www.w3.org/2000/svg"
//                   className="h-4 w-4"
//                   viewBox="0 0 20 20"
//                   fill="currentColor"
//                 >
//                   <path
//                     fillRule="evenodd"
//                     d="M6.293 9.293a1 1 0 011.414 0L10 11.586l2.293-2.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z"
//                     clipRule="evenodd"
//                   />
//                 </svg>
//               </button>
//             )}

//             <div className="flex-1">
//               <h3 className="text-base font-semibold leading-6">
//                 <Link to={item.url} className="inline-flex items-baseline gap-2 no-underline text-inherit">
//                   <span className="text-sm text-gray-500">{applyHighlight(creCode, filter)}:</span>
//                   <span className="ml-1">{applyHighlight(String(creName), filter)}</span>
//                 </Link>
//               </h3>

//               <div className="mt-2">
//                 <LinkedStandards
//                   linkedTo={linkedTo}
//                   applyHighlight={applyHighlight}
//                   creCode={creCode}
//                   filter={filter}
//                 />
//               </div>
//             </div>
//           </div>

//           {contains.length > 0 && !isCollapsed(item.id) && (
//             <ul className="mt-3 pl-6">
//               {contains.map((child) => (
//                 <React.Fragment key={Math.random()}>{processNode(child.document)}</React.Fragment>
//               ))}
//             </ul>
//           )}
//         </div>
//       </li>
//     );
//   }

//   function update(event: React.KeyboardEvent<HTMLInputElement> | React.ChangeEvent<HTMLInputElement>) {
//     const target = event.target as HTMLInputElement;
//     setFilter(target.value.toLowerCase());
//   }

//   return (
//     <>
//       <main id="explorer-content" className="p-7 mt-[var(--header-height)]">
//         <h1 className="text-2xl font-bold mb-2">Open CRE Explorer</h1>
//         <p className="mb-4 ">
//           A visual explorer of Open Common Requirement Enumerations (CREs). Originally created by:{' '}
//           <a
//             target="_blank"
//             rel="noreferrer"
//             href="https://zeljkoobrenovic.github.io/opencre-explorer/"
//             className="text-blue-600 underline"
//           >
//             Zeljko Obrenovic
//           </a>
//           .
//         </p>
//         <div id="explorer-wrapper" className="flex flex-col md:flex-row md:items-start gap-6 mb-6">
//           <div className="search-field flex flex-col">
//             <input
//               id="filter"
//               type="text"
//               placeholder="Search Explorer..."
//               onKeyUp={update}
//               onChange={update}
//               className="text-base h-10 w-100 mb-2 rounded-sm border border-gray-400 px-2"
//             />
//             <div id="search-summary" />
//             <div id="graphs-menu" className="mt-1 flex items-center">
//               <div className="text-base font-bold mr-2">Explore visually:</div>

//               <span className="flex text-blue-600 hover:text-blue-800 text-sm space-x-2">
//                 <a href="/explorer/force_graph" className="pr-2 border-r border-gray-400">
//                   Dependency Graph
//                 </a>



//                 <a href="/explorer/circles" className-="pl-2">
//                   Zoomable circles
//                 </a>
//               </span>
//             </div>
//           </div>

//         </div>

//         <LoadingAndErrorIndicator loading={loading} error={null} />

//         <ul className="list-none p-0">
//           {filteredTree?.map((item) => {
//             return processNode(item);
//           })}
//         </ul>
//       </main>
//     </>
//   );
// };
