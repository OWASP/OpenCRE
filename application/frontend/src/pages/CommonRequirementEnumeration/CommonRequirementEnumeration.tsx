import './commonRequirementEnumeration.scss';

import React, { useContext, useEffect, useMemo, useState } from 'react';
import { useQuery } from 'react-query';
import { useParams } from 'react-router-dom';

import { DocumentNode } from '../../components/DocumentNode';
import { ClearFilterButton, FilterButton } from '../../components/FilterButton/FilterButton';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';
import { applyFilters, filterContext } from '../../hooks/applyFilters';
import { Document } from '../../types';
import { groupLinksByType } from '../../utils';
import { getDocumentDisplayName, getDocumentTypeText, orderLinksByType } from '../../utils/document';

export const CommonRequirementEnumeration = () => {
  const { id } = useParams();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const globalState = useContext(filterContext);

  const { error, data, refetch } = useQuery<{ data: Document }, string>(
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
  let filteredCRE;
  if (cre != undefined) {
    filteredCRE = applyFilters(JSON.parse(JSON.stringify(cre))); // dirty deepcopy
  }
  let currentUrlParams = new URLSearchParams(window.location.search);
  let display: Document;
  display = currentUrlParams.get('applyFilters') === 'true' ? filteredCRE : cre;

  const linksByType = useMemo(() => (display ? orderLinksByType(groupLinksByType(display)) : {}), [display]);
  return (
    <div className="cre-page">
      <LoadingAndErrorIndicator loading={loading} error={error} />
      {!loading && !error && display && (
        <>
          <h4 className="cre-page__heading">{display.name}</h4>
          <h5 className="cre-page__sub-heading">CRE: {display.id}</h5>
          <div className="cre-page__description">{display.description}</div>
          {display && display.hyperlink && (
            <>
              <span>Reference: </span>
              <a href={display?.hyperlink} target="_blank">
                {' '}
                {display.hyperlink}
              </a>
            </>
          )}

          {currentUrlParams.get('applyFilters') === 'true' ? (
            <div className="cre-page__filters">
              Filtering on:
              {currentUrlParams.getAll('filters').map((filter) => (
                <b key={filter}>{filter.replace('s:', '').replace('c:', '')}, </b>
              ))}
              <ClearFilterButton />
            </div>
          ) : (
            ''
          )}
          <div className="cre-page__links-container">
            {Object.keys(linksByType).length > 0 &&
              Object.entries(linksByType).map(([type, links]) => {
                const sortedResults = links.sort((a, b) =>
                  getDocumentDisplayName(a.document).localeCompare(getDocumentDisplayName(b.document))
                );
                let lastDocumentName = sortedResults[0].document.name;
                return (
                  <div className="cre-page__links" key={type}>
                    <div className="cre-page__links-eader">
                      <b>Which {getDocumentTypeText(type, links[0].document.doctype)}</b>:
                      {/* Risk here of mixed doctype in here causing odd output */}
                    </div>
                    {sortedResults.map((link, i) => {
                      const temp = (
                        <div key={i} className="accordion ui fluid styled cre-page__links-container">
                          {lastDocumentName !== link.document.name && <span style={{ margin: '5px' }} />}
                          <DocumentNode node={link.document} linkType={type} />
                          <FilterButton document={link.document} />
                        </div>
                      );
                      lastDocumentName = link.document.name;
                      return temp;
                    })}
                  </div>
                );
              })}
          </div>
        </>
      )}
    </div>
  );
};
