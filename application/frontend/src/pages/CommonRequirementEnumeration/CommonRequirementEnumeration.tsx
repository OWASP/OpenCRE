import axios from 'axios';
import React, { useEffect, useMemo, useState } from 'react';
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
  const { id } = useParams<{ id: string }>();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | Object | null>(null);
  const [data, setData] = useState<Document | null>();

  useEffect(() => {
    setLoading(true);
    window.scrollTo(0, 0);

    axios
      .get(`${apiUrl}/id/${id}`)
      .then(function (response) {
        setError(null);
        setData(response?.data?.data);
      })
      .catch(function (axiosError) {
        if (axiosError.response.status === 404) {
          setError('CRE does not exist in the DB, please check your search parameters');
        } else {
          setError(axiosError.response);
        }
      })
      .finally(() => {
        setLoading(false);
      });
  }, [id]);

  const cre = data;
  let filteredCRE;
  if (cre != undefined) {
    filteredCRE = applyFilters(JSON.parse(JSON.stringify(cre))); // dirty deepcopy
  }
  let currentUrlParams = new URLSearchParams(window.location.search);
  let display: Document;
  display = currentUrlParams.get('applyFilters') === 'true' ? filteredCRE : cre;

  const linksByType = useMemo(() => (display ? orderLinksByType(groupLinksByType(display)) : {}), [display]);

  return (
    <div
      className="cre-page"
      style={{
        padding: '30px',
        marginTop: 'var(--header-height)',
        marginBottom: 0
      }}
    >
      <LoadingAndErrorIndicator loading={loading} error={error} />
      {!loading && !error && display && (
        <>
          <h4
            className="cre-page-heading"
            style={{
              fontSize: '2rem',
              marginBottom: 0
            }}
          >
            {display.name}
          </h4>
          <h5
            className="cre-page-sub-heading"
            style={{
              color: '#999',
              marginTop: 0,
              fontSize: '1.2rem'
            }}
          >
            CRE: {display.id}
          </h5>
          <div
            className="cre-page-description"
            style={{ width: '50%' }}
          >
            {display.description}
          </div>
          {display && display.hyperlink && (
            <>
              <span>Reference: </span>
              <a
                href={display?.hyperlink}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:text-blue-800"
              >
                {display.hyperlink}
              </a>
            </>
          )}

          {currentUrlParams.get('applyFilters') === 'true' ? (
            <div
              className="cre-page-filters"
              style={{ marginTop: '10px' }}
            >
              Filtering on:{' '}
              {currentUrlParams.getAll('filters').map((filter) => (
                <b key={filter}>{filter.replace('s:', '').replace('c:', '')}, </b>
              ))}
              <ClearFilterButton />
            </div>
          ) : (
            ''
          )}
          <div
            className="cre-page-links-container"
            style={{ marginTop: '10px' }}
          >
            {Object.keys(linksByType).length > 0 &&
              Object.entries(linksByType).map(([type, links]) => {
                const sortedResults = links.sort((a, b) =>
                  getDocumentDisplayName(a.document).localeCompare(getDocumentDisplayName(b.document))
                );
                let lastDocumentName = sortedResults[0].document.name;
                return (
                  <div
                    className="cre-page-links"
                    key={type}
                    style={{
                      paddingTop: '20px'
                    }}
                  >
                    <div
                      className="cre-page-links-header"
                      style={{ marginBottom: '10px' }}
                    >
                      <b>Which {getDocumentTypeText(type, links[0].document.doctype)}</b>:
                    </div>
                    {sortedResults.map((link, i) => {
                      const temp = (
                        <div
                          key={i}
                          className="cre-page-link-item"
                          style={{
                            paddingTop: 0,
                            border: 'none',
                            borderRadius: i === 0 ? '0.28571429rem 0' : (i === sortedResults.length - 1 ? '0 0.28571429rem' : 0),
                            marginTop: 0,
                            boxShadow: i === 0
                              ? '0 1px 2px 0 rgba(34, 36, 38, .15), 0 0 0 1px rgba(34, 36, 38, .15)'
                              : '0 1px 2px 0 rgba(34, 36, 38, .15), 0 1px 0 1px rgba(34, 36, 38, .15)'
                          }}
                        >
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
