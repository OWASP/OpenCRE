import axios from 'axios';
import React, { FunctionComponent, useContext, useEffect, useMemo, useState } from 'react';
import { Link, useHistory } from 'react-router-dom';
import { TYPE_AUTOLINKED_TO, TYPE_CONTAINS, TYPE_IS_PART_OF, TYPE_RELATED } from '../../const';
import { useEnvironment } from '../../hooks';
import { applyFilters } from '../../hooks/applyFilters';
import { Document } from '../../types';
import { getDocumentDisplayName, groupLinksByType } from '../../utils';
import { getApiEndpoint, getDocumentTypeText, getInternalUrl } from '../../utils/document';
import { FilterButton } from '../FilterButton/FilterButton';
import { LoadingAndErrorIndicator } from '../LoadingAndErrorIndicator';
import { ChevronDown, Circle, ExternalLink, ChevronRight } from 'lucide-react';




export interface DocumentNode {
  node: Document;
  linkType: string;
  hasLinktypeRelatedParent?: Boolean;
}

const linkTypesToNest = [TYPE_IS_PART_OF, TYPE_RELATED, TYPE_AUTOLINKED_TO];
const linkTypesExcludedInNesting = [TYPE_CONTAINS];
const linkTypesExcludedWhenNestingRelatedTo = [TYPE_RELATED, TYPE_IS_PART_OF, TYPE_CONTAINS];

export const DocumentNode: FunctionComponent<DocumentNode> = ({
  node,
  linkType,
  hasLinktypeRelatedParent,
}) => {
  const [expanded, setExpanded] = useState<boolean>(false);
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

  useEffect(() => {
    if (!isStandard && linkTypesToNest.includes(linkType)) {
      setLoading(true);
      axios
        .get(getApiEndpoint(node, apiUrl))
        .then(function (response) {
          setLoading(false);
          setNestedNode(response.data.data);
          setExpanded(true);
          setError('');
        })
        .catch(function (axiosError) {
          setLoading(false);
          setError(axiosError);
        });
    }
  }, [id]);

  const fetchedNodeHasLinks = () => {
    return usedNode.links && usedNode.links.length > 0;
  };

  const hasActiveLinks = () => {
    return getTopicsToDisplayOrderdByLinkType().length > 0;
  };

  const isNestedInRelated = (): Boolean => {
    return hasLinktypeRelatedParent || linkType === TYPE_RELATED;
  };

  const getTopicsToDisplayOrderdByLinkType = () => {
    return Object.entries(linksByType)
      .filter(([type, _]) => !linkTypesExcludedInNesting.includes(type))
      .filter(([type, _]) =>
        isNestedInRelated() ? !linkTypesExcludedWhenNestingRelatedTo.includes(type) : true
      );
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
      </>
    );
  };

  const HyperlinkIcon = (hyperlink) => {
    if (!hyperlink.hyperlink) {
      return <></>;
    }

    return (
      <a
        href={hyperlink.hyperlink}
        target="_blank"
        rel="noopener noreferrer"
        style={{
          color: '#2185d0',
          fontSize: '0.9em',
          paddingLeft: '0.5em',
          display: 'inline-flex',
          alignItems: 'center',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = '#115c96';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = '#2185d0';
        }}
      >
        <ExternalLink size={14} />
      </a>
    );
  };

  const SimpleView = () => {
    const [isHovered, setIsHovered] = useState(false);

    return (
      <>
        <div
          className="title external-link document-node"
          style={{
            paddingTop: 0,
            paddingBottom: '0.25em',
          }}
        >
          <Link
            to={getInternalUrl(usedNode)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              textDecoration: 'none',
              color: isHovered ? 'rgba(0, 0, 0, 0.87)' : 'rgba(0, 0, 0, 0.4)',
            }}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
          >
            <Circle
              size={8}
              fill="currentColor"
              style={{
                fontSize: '0.5em',
                position: 'relative',
                marginRight: '0.6rem',
                marginLeft: '0.3rem',
                flexShrink: 0,
              }}
            />
            <span>{getDocumentDisplayName(usedNode)}</span>
          </Link>
          {hasExternalLink && <HyperlinkIcon hyperlink={usedNode.hyperlink} />}
        </div>
        <div className="content"></div>
      </>
    );
  };

  const NestedView = () => {
    return (
      <>
        <LoadingAndErrorIndicator loading={loading} error={error} />
        <div
          className={`title ${active} document-node`}
          style={{
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            paddingTop: 0,
            paddingBottom: '0.25em',
          }}
        >
          <div
            onClick={() => setExpanded(!expanded)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              flex: 1,
            }}
          >
            <ChevronRight
              size={16}
              style={{
                marginRight: '8px',
                transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
                transition: 'transform 0.2s ease',
                flexShrink: 0,
                color: '#4183c4',
              }}
            />
            <Link
              to={getInternalUrl(usedNode)}
              style={{
                color: '#4183c4',
                textDecoration: 'none',
              }}
            >
              {getDocumentDisplayName(usedNode)}
            </Link>
          </div>
        </div>
        <div className={`content${active} document-node`}>
          <Hyperlink hyperlink={usedNode.hyperlink} />
          {expanded &&
            getTopicsToDisplayOrderdByLinkType().map(([type, links], idx) => {
              const sortedResults = links.sort((a, b) =>
                getDocumentDisplayName(a.document).localeCompare(getDocumentDisplayName(b.document))
              );
              let lastDocumentName = sortedResults[0].document.name;
              return (
                <div
                  className="document-node__link-type-container"
                  key={type}
                >
                  {idx > 0 && (
                    <hr
                      style={{
                        borderColor: 'transparent',
                        margin: '15px 0'
                      }}
                    />
                  )}
                  <div>
                    <b>Which {getDocumentTypeText(type, links[0].document.doctype, node.doctype)}</b>:
                  </div>
                  <div>
                    <div className="accordion-content">
                      {sortedResults.map((link, i) => {
                        const temp = (
                          <div key={Math.random()}>
                            {lastDocumentName !== link.document.name && <span style={{ margin: '5px' }} />}
                            <DocumentNode
                              node={link.document}
                              linkType={type}
                              hasLinktypeRelatedParent={isNestedInRelated()}
                              key={Math.random()}
                            />
                            <FilterButton document={link.document} />
                          </div>
                        );
                        lastDocumentName = link.document.name;
                        return temp;
                      })}
                    </div>
                  </div>
                </div>
              );
            })}
        </div>
      </>
    );
  };

  return hasActiveLinks() ? <NestedView /> : <SimpleView />;
};
