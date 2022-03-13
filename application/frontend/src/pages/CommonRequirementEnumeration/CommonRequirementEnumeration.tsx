import './commonRequirementEnumeration.scss';

import React, { useEffect, useMemo, useState, useContext } from 'react';
import { useQuery } from 'react-query';
import { useParams } from 'react-router-dom';

import { DocumentNode } from '../../components/DocumentNode';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { DOCUMENT_TYPE_NAMES } from '../../const';
import { useEnvironment } from '../../hooks';
import { Document } from '../../types';
import { groupLinksByType } from '../../utils';
import { applyFilters, filterContext } from '../../hooks/applyFilters';
import { ClearFilterButton, FilterButton } from '../../components/FilterButton/FilterButton';

export const CommonRequirementEnumeration = () => {
  const { id } = useParams();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const globalState = useContext(filterContext)

  const { error, data, refetch } = useQuery<{ data: Document; }, string>(
    'cre',
    () => fetch(`${apiUrl}/id/${id}`).then((res) => res.json()),
    {
      retry: false,
      enabled: false,
      onSettled: () => {
        setLoading(false);
      },
    }
  );

  useEffect(() => {
    window.scrollTo(0, 0);
    setLoading(true);
    refetch();
  }, [id]);

  const cre = data?.data;
  let filteredCRE
  if(cre != undefined){
    filteredCRE = applyFilters(JSON.parse(JSON.stringify(cre))) // dirty deepcopy
  }
  let currentUrlParams = new URLSearchParams(window.location.search);
  let display:Document
  display = currentUrlParams.get("applyFilters") === "true"? filteredCRE:cre

  const linksByType = useMemo(() => (display ? groupLinksByType(display) : {}), [display]);

  return (
    <div className="cre-page">
      <LoadingAndErrorIndicator loading={loading} error={error} />
      {!loading && !error && display && (
        <>
          <h4 className="cre-page__heading">{display.name}</h4>
          <h5 className="cre-page__sub-heading">{display.id}</h5>
          <div className="cre-page__description">{display.description}</div>
          { display && display.hyperlink &&
            <>
              <span>Reference: </span>
              <a href={display?.hyperlink} target="_blank"> { display.hyperlink }</a>
            </>
          }
          {display.tags?
          <div className="cre-page__tags">Tags:{display.tags.map((tag) => ( <b>{tag} </b>))}</div>:""}

          {currentUrlParams.get("applyFilters")==="true"?
          <div className="cre-page__filters">
          Filtering on:
            {currentUrlParams.getAll("filters").map((filter)=>(
              <b key={filter}>{filter.replace("s:","").replace("c:","")}, </b>))}

          <ClearFilterButton/>
          </div>:""}
          <div className="cre-page__links-container">
            {Object.keys(linksByType).length > 0 &&
              Object.entries(linksByType).map(([type, links]) => (
                <div className="cre-page__links" key={type}>
                  <div className="cre-page__links-eader">
                  {display.doctype}:{display.id}: {display.name} <b>{DOCUMENT_TYPE_NAMES[type]}</b>:
                  </div>
                  {links.map((link, i) => (
                    <div key={i} className="accordion ui fluid styled cre-page__links-container">
                      <DocumentNode node={link.document} linkType={type} />
                      <FilterButton document={link.document}/>
                    </div>
                  ))}
                </div>
              ))}
          </div>
        </>
      )}
    </div>
  );
};
