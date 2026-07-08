import './documentNode.scss';

import axios from 'axios';
import React, { FunctionComponent, useContext, useEffect, useMemo, useState } from 'react';
import { Link, useHistory, useLocation } from 'react-router-dom';
import { Icon } from 'semantic-ui-react';

import {
  CRE,
  TYPE_AUTOLINKED_TO,
  TYPE_CONTAINS,
  TYPE_IS_PART_OF,
  TYPE_LINKED_TO,
  TYPE_RELATED,
} from '../../const';
import { useEnvironment } from '../../hooks';
import { applyFilters } from '../../hooks/applyFilters';
import { Document } from '../../types';
import { groupLinksByType } from '../../utils';
import {
  getApiEndpoint,
  getDocumentTypeText,
  getInternalUrl,
  getTopicDisplayName,
} from '../../utils/document';
import { FilterButton } from '../FilterButton/FilterButton';
import { LoadingAndErrorIndicator } from '../LoadingAndErrorIndicator';

const MAX_LENGTH_FOR_AUTO_EXPAND = 5;
export interface DocumentNode {
  node: Document;
  linkType: string;
  hasLinktypeRelatedParent?: Boolean;
}

const linkTypesToNest = [TYPE_IS_PART_OF, TYPE_RELATED, TYPE_AUTOLINKED_TO];
const linkTypesExcludedInNesting = [TYPE_CONTAINS];
const linkTypesExcludedWhenNestingRelatedTo = [TYPE_RELATED, TYPE_IS_PART_OF, TYPE_CONTAINS];
const linkDisplayOrder = [TYPE_LINKED_TO, TYPE_AUTOLINKED_TO, TYPE_CONTAINS, TYPE_IS_PART_OF, TYPE_RELATED];

export const DocumentNode: FunctionComponent<DocumentNode> = ({
  node,
  linkType,
  hasLinktypeRelatedParent,
}) => {
  const [expanded, setExpanded] = useState<boolean>(false);
  const [showAll, setShowAll] = useState<Record<number, boolean>>({});
  const isStandard = node.doctype in ['Tool', 'Code', 'Standard'];
  const { apiUrl } = useEnvironment();
  const [nestedNode, setNestedNode] = useState<Document>();
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const id = isStandard ? node.name : node.id;
  const active = expanded ? ' active' : '';
  const history = useHistory();
  var usedNode = applyFilters(nestedNode || node);
  const hasExternalLink = Boolean(usedNode.hyperlink);
  const linksByType = useMemo(() => groupLinksByType(usedNode), [usedNode]);
  let currentUrlParams = new URLSearchParams(window.location.search);
  const { pathname } = useLocation();
  const isCrePath = useMemo(() => pathname.includes(CRE), [pathname]);

  const isNestedInRelated = hasLinktypeRelatedParent || linkType === TYPE_RELATED;

  const getTopicsToDisplayOrderdByLinkType = () => {
    return linkDisplayOrder
      .map((type) => [type, linksByType[type]] as [string, any])
      .filter(([_, links]) => Array.isArray(links) && links.length > 0)
      .filter(([type, _]) => !linkTypesExcludedInNesting.includes(type))
      .filter(([type, _]) =>
        isNestedInRelated ? !linkTypesExcludedWhenNestingRelatedTo.includes(type) : true
      );
  };

  const topicsToDisplay = useMemo(
    () => getTopicsToDisplayOrderdByLinkType(),
    [linksByType, isNestedInRelated]
  );

  useEffect(() => {
    const isAllowedToAutoExpandByLength =
      topicsToDisplay.map(([, links]) => links).reduce((prev, cur) => prev.concat(cur), []).length <=
      MAX_LENGTH_FOR_AUTO_EXPAND;
    const shouldCollapseRelatedByDefault = linkType === TYPE_RELATED;
    setExpanded(isCrePath && !shouldCollapseRelatedByDefault ? isAllowedToAutoExpandByLength : false);
  }, [topicsToDisplay, isCrePath, linkType]);

  useEffect(() => {
    if (!isStandard && linkTypesToNest.includes(linkType)) {
      setLoading(true);
      axios
        .get(getApiEndpoint(node, apiUrl))
        .then(function (response) {
          setLoading(false);
          setNestedNode(response.data.data);
          setExpanded(linkType !== TYPE_RELATED);
          setError('');
        })
        .catch(function (axiosError) {
          setLoading(false);
          setError(axiosError);
        });
    }
  }, [id, linkType]);

  const fetchedNodeHasLinks = () => {
    return usedNode.links && usedNode.links.length > 0;
  };

  const hasActiveLinks = () => {
    return topicsToDisplay.length > 0;
  };

  const Hyperlink = (hyperlink) => {
    if (!hyperlink.hyperlink) {
      return <></>;
    }

    return (
      <>
        <span>Reference:</span>
        <a href={hyperlink.hyperlink} target="_blank" rel="noopener noreferrer">
          {' '}
          {hyperlink.hyperlink}
        </a>
        <a
          href={hyperlink.hyperlink}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="Open reference in new tab"
        >
          <Icon name="external" />
        </a>
      </>
    );
  };

  const HyperlinkIcon = (hyperlink) => {
    if (!hyperlink.hyperlink) {
      return <></>;
    }

    return (
      <a href={hyperlink.hyperlink} target="_blank" rel="noopener noreferrer">
        <Icon name="external" />
      </a>
    );
  };
  const SimpleView = () => {
    return (
      <>
        <div className={`title external-link document-node f2`}>
          <Link to={getInternalUrl(usedNode)}>
            <i aria-hidden="true" className="circle icon"></i>
            {getTopicDisplayName(usedNode)}
          </Link>
          <HyperlinkIcon hyperlink={usedNode.hyperlink} />
        </div>
        <div className={`content`}></div>
      </>
    );
  };

  const NestedView = () => {
    return (
      <>
        <LoadingAndErrorIndicator loading={loading} error={error} />
        <div className={`title ${active} document-node`} onClick={() => setExpanded(!expanded)}>
          <i aria-hidden="true" className="dropdown icon"></i>
          <Link to={getInternalUrl(usedNode)}>{getTopicDisplayName(usedNode)}</Link>
        </div>
        <div className={`content${active} document-node`}>
          <Hyperlink hyperlink={usedNode.hyperlink} />
          {expanded &&
            topicsToDisplay.map(([type, links], idx) => {
              const sortedResults = [...links].sort((a, b) =>
                getTopicDisplayName(a.document).localeCompare(getTopicDisplayName(b.document))
              );
              return (
                <div className="document-node__link-type-container" key={`${type}-${idx}`}>
                  {idx > 0 && <hr style={{ borderColor: 'transparent', margin: '20px 0' }} />}
                  <div>
                    <b>Which {getDocumentTypeText(type, links[0].document.doctype, node.doctype)}</b>:
                    {/* Risk here of mixed doctype in here causing odd output */}
                  </div>
                  <div>
                    <div className="accordion ui fluid styled f0">
                      {sortedResults
                        .slice(0, showAll[idx] ? sortedResults.length : MAX_LENGTH_FOR_AUTO_EXPAND)
                        .map((link, i) => (
                          <div
                            key={`document-node-container-${type}-${idx}-${i}`}
                            style={{ marginBottom: '4px' }}
                          >
                            <DocumentNode
                              node={link.document}
                              linkType={type}
                              hasLinktypeRelatedParent={isNestedInRelated as boolean}
                              key={`document-sub-node-${type}-${idx}-${i}`}
                            />
                            <FilterButton document={link.document} />
                          </div>
                        ))}
                    </div>
                    {sortedResults.length > MAX_LENGTH_FOR_AUTO_EXPAND && (
                      <button
                        onClick={() => setShowAll((prev) => ({ ...prev, [idx]: !prev[idx] }))}
                        style={{ marginTop: '8px', cursor: 'pointer' }}
                      >
                        {showAll[idx] ? 'Show less ▲' : 'Show more ▼'}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          {/* <FilterButton/> */}
        </div>
      </>
    );
  };

  return hasActiveLinks() ? <NestedView /> : <SimpleView />;
};
