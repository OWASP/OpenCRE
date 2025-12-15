import axios from 'axios';
import React, { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { DocumentNode } from '../../components/DocumentNode';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { DOCUMENT_TYPES, DOCUMENT_TYPE_NAMES, TOOL } from '../../const';
import { useEnvironment } from '../../hooks';
import { Document, PaginatedResponse } from '../../types';
import { getDocumentDisplayName, groupLinksByType } from '../../utils';
import { getDocumentTypeText } from '../../utils/document';
import { ChevronLeft, ChevronRight } from 'lucide-react';



export const StandardSection = () => {
  const { id, section, sectionID, subsection } = useParams<{
    id: string;
    section: string;
    sectionID: string;
    subsection: string;
  }>();
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

  const getSubsectionParameter = (): string => {
    return subsection ? `&subsection=${encodeURIComponent(subsection)}` : '';
  };

  useEffect(() => {
    window.scrollTo(0, 0);
    setLoading(true);
    axios
      .get(
        `${apiUrl}/standard/${id}?page=${page}${getSectionParameter()}${getSectionIDParameter()}${getSubsectionParameter()}`
      )
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
  }, [id, section, sectionID, page, subsection]);

  const documents = data?.standards || [];
  const document = documents[0];
  const linksByType = useMemo(() => (document ? groupLinksByType(document) : {}), [document]);
  const version = document?.version;

  const renderPagination = () => {
    if (!data || data.total_pages <= 1) return null;

    const pages: number[] = [];
    for (let i = 1; i <= data.total_pages; i++) {
      pages.push(i);
    }

    return (
      <div className="pagination-container" style={{ marginTop: '15px', display: 'flex', justifyContent: 'center' }}>
        <nav className="inline-flex items-center gap-1">
          <button
            onClick={() => page > 1 && setPage(page - 1)}
            disabled={page === 1}
            className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronLeft size={16} />
          </button>
          {pages.map((pageNum) => (
            <button
              key={pageNum}
              onClick={() => setPage(pageNum)}
              className={`inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-md border ${page === pageNum
                ? 'bg-blue-600 text-white border-blue-600'
                : 'border-gray-300 bg-white hover:bg-gray-50 text-gray-700'
                }`}
            >
              {pageNum}
            </button>
          ))}
          <button
            onClick={() => page < data.total_pages && setPage(page + 1)}
            disabled={page === data.total_pages}
            className="inline-flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronRight size={16} />
          </button>
        </nav>
      </div>
    );
  };

  return (
    <>
      <div
        className="standard-page section-page"
        style={{
          padding: '30px',
          marginTop: 'var(--header-height)',
          marginBottom: 0
        }}
      >
        <h5
          className="standard-page-heading"
          style={{
            fontSize: '2rem',
            marginBottom: 0
          }}
        >
          {getDocumentDisplayName(document)}
        </h5>
        {document && document.hyperlink && (
          <>
            <span>Reference: </span>
            <a
              href={document?.hyperlink}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:text-blue-800"
            >
              {document.hyperlink}
            </a>
          </>
        )}
        <LoadingAndErrorIndicator loading={loading} error={error} />
        {!loading && !error && (
          <div className="cre-page-links-container" style={{ marginTop: '10px' }}>
            {Object.keys(linksByType).length > 0 ? (
              Object.entries(linksByType).map(([type, links]) => (
                <div className="cre-page-links" key={type} style={{ paddingTop: '20px' }}>
                  <div className="cre-page-links-header" style={{ marginBottom: '10px' }}>
                    <b>Which {getDocumentTypeText(type, links[0].document.doctype, document.doctype)}</b>:
                    {/* Risk here of mixed doctype in here causing odd output */}
                  </div>
                  {links
                    .sort((a, b) =>
                      getDocumentDisplayName(a.document).localeCompare(getDocumentDisplayName(b.document))
                    )
                    .map((link, i) => (
                      <div
                        key={i}
                        className="cre-page-links-container-item"
                        style={{
                          marginTop: '10px',
                          wordBreak: window.innerWidth < 600 ? 'break-word' : 'normal'
                        }}
                      >
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

        {renderPagination()}
      </div>
    </>
  );
};
