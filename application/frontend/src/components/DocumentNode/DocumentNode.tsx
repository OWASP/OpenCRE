import './documentNode.scss';

import React, { FunctionComponent, useMemo, useState, useEffect, useContext } from 'react';
import { Link, useHistory } from 'react-router-dom';

import { DOCUMENT_TYPE_NAMES, TYPE_IS_PART_OF, TYPE_CONTAINS, TYPE_LINKED_TO, TYPE_RELATED } from '../../const';
import { Document } from '../../types';
import { getDocumentDisplayName, groupLinksByType } from '../../utils';
import { useEnvironment } from '../../hooks';
import axios from 'axios';
import { LoadingAndErrorIndicator } from '../LoadingAndErrorIndicator';
import { getApiEndpoint, getInternalUrl } from '../../utils/document';
import { Button } from 'semantic-ui-react';
import { FilterButton } from '../FilterButton/FilterButton';
import { applyFilters } from '../../hooks/applyFilters';

export interface DocumentNode {
  node: Document,
  linkType: string,
  hasLinktypeRelatedParent?: Boolean,
}

const linkTypesToNest = [TYPE_IS_PART_OF, TYPE_RELATED]
const linkTypesExcludedInNesting = [TYPE_CONTAINS]
const linkTypesExcludedWhenNestingRelatedTo = [TYPE_RELATED, TYPE_IS_PART_OF, TYPE_CONTAINS]

export const DocumentNode: FunctionComponent<DocumentNode> = ({ node, linkType, hasLinktypeRelatedParent }) => {
  const [expanded, setExpanded] = useState<boolean>(false);
  const isStandard = node.doctype in ["Tool","Code", "Standard"];
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
      axios.get(getApiEndpoint(node, apiUrl))
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
  }

  const hasActiveLinks = () => {
    return getTopicsToDisplayOrderdByLinkType().length > 0;
  }

  const isNestedInRelated = (): Boolean => {
    return hasLinktypeRelatedParent || (linkType === TYPE_RELATED);
  }

  const getTopicsToDisplayOrderdByLinkType = () => {
    return Object.entries(linksByType)
      .filter(([type, _]) => !linkTypesExcludedInNesting.includes(type))
      .filter(([type, _]) => isNestedInRelated() ? !linkTypesExcludedWhenNestingRelatedTo.includes(type) : true)
  }

  const Hyperlink = (hyperlink) => {
    if (!hyperlink.hyperlink) {
      return <></>;
    }

    return <>
      <span>
        Reference:
      </span>
      <a href={hyperlink.hyperlink} target="_blank"> {hyperlink.hyperlink}</a>
    </>
  }
  const SimpleView = () => {
    return <>
      <div className={`title external-link document-node f2`}>
        <Link to={getInternalUrl(usedNode)}>
          <i aria-hidden="true" className="circle icon"></i>
          {getDocumentDisplayName(usedNode)}
        </Link>
      </div>
      <div className={`content`}></div>

    </>
  }

  const NestedView = () => {
    return <>

      <LoadingAndErrorIndicator loading={loading} error={error} />
      <div className={`title${active} document-node`} onClick={() => setExpanded(!expanded)}>
        <i aria-hidden="true" className="dropdown icon"></i>
        <Link to={getInternalUrl(usedNode)}>
          {getDocumentDisplayName(usedNode)}
        </Link>
      </div>
      <div className={`content${active} document-node`}>
        <Hyperlink hyperlink={usedNode.hyperlink} />
        {expanded
          && getTopicsToDisplayOrderdByLinkType().map(([type, links]) => {
            return (
              <div className="document-node__link-type-container" key={type}>
                <div>
                  <span >{usedNode.doctype}: {usedNode.name} - {usedNode.section} </span>
                  <b> {DOCUMENT_TYPE_NAMES[type]}</b>:
                </div>
                <div>
                  <div className="accordion ui fluid styled f0">
                    {links.map((link, i) =>
                        <div key={Math.random()}>
                          <DocumentNode node={link.document} linkType={type} hasLinktypeRelatedParent={isNestedInRelated()} key={Math.random()} />
                          <FilterButton document={link.document}/>
                        </div> 
                    )
                    }
                  </div>
                </div>
              </div>
            );
          })}
          {/* <FilterButton/> */}
      </div>
    </>

  }

  return hasActiveLinks() ? <NestedView /> : <SimpleView />;
};
