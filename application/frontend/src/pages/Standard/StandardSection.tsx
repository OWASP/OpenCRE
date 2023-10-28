import './standard.scss';

import axios from 'axios';
import React, { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Pagination } from 'semantic-ui-react';

import { DocumentNode } from '../../components/DocumentNode';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { DOCUMENT_TYPES, DOCUMENT_TYPE_NAMES, TOOL } from '../../const';
import { useEnvironment } from '../../hooks';
import { Document, PaginatedResponse } from '../../types';
import { getDocumentDisplayName, groupLinksByType } from '../../utils';
import { getDocumentTypeText } from '../../utils/document';

export const StandardSection = () => {
  const { id, section, sectionID } = useParams();
  const { apiUrl } = useEnvironment();
  const [page, setPage] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | Object | null>(null);
  const [data, setData] = useState<PaginatedResponse | null>();

  const getSectionParameter = (): string => {
    return section ? `&section=${encodeURIComponent(section)}` : '';
  };
  const getSectionIDParameter = (): string => {
    return sectionID ? `&sectionID=${encodeURIComponent(sectionID)}` : '';
  };

  useEffect(() => {
    window.scrollTo(0, 0);
    setLoading(true);
    axios
      .get(`${apiUrl}/standard/${id}?page=${page}${getSectionParameter()}${getSectionIDParameter()}`)
      .then(function (response) {
        setError(null);
        setData(response.data);
      })
      .catch(function (axiosError) {
        if (axiosError.response.status === 404) {
          setError('Standard does not exist in the DB, please check your search parameters');
        } else {
          setError(axiosError.response);
        }
      })
      .finally(() => {
        setLoading(false);
      });
  }, [id, section, sectionID, page]);

  const documents = data?.standards || [];
  const document = documents[0];
  const linksByType = useMemo(() => (document ? groupLinksByType(document) : {}), [document]);
  const version = document?.version;

  return (
    <>
      <div className="standard-page section-page">
        <h5 className="standard-page__heading">{getDocumentDisplayName(document)}</h5>
        {document && document.hyperlink && (
          <>
            <span>Reference: </span>
            <a href={document?.hyperlink} target="_blank">
              {' '}
              {document.hyperlink}
            </a>
          </>
        )}
        <LoadingAndErrorIndicator loading={loading} error={error} />
        {!loading && !error && (
          <div className="cre-page__links-container">
            {Object.keys(linksByType).length > 0 ? (
              Object.entries(linksByType).map(([type, links]) => (
                <div className="cre-page__links" key={type}>
                  <div className="cre-page__links-header">
                    <b>Which {getDocumentTypeText(type, links[0].document.doctype, document.doctype)}</b>:
                    {/* Risk here of mixed doctype in here causing odd output */}
                  </div>
                  {links
                    .sort((a, b) =>
                      getDocumentDisplayName(a.document).localeCompare(getDocumentDisplayName(b.document))
                    )
                    .map((link, i) => (
                      <div key={i} className="accordion ui fluid styled cre-page__links-container">
                        <DocumentNode node={link.document} linkType={type} />
                      </div>
                    ))}
                </div>
              ))
            ) : (
              <b>
                "This document has no links yet, please open a ticket at
                https://github.com/OWASP/common-requirement-enumeration with your suggested mapping"
              </b>
            )}
          </div>
        )}

        {data && data.total_pages > 0 && (
          <div className="pagination-container">
            <Pagination
              defaultActivePage={1}
              onPageChange={(_, d) => setPage(d.activePage as number)}
              totalPages={data.total_pages}
            />
          </div>
        )}
      </div>
    </>
  );
};
