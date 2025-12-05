import axios from 'axios';
import React, { useEffect, useState } from 'react';
import { useLocation, useParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { DocumentNode } from '../../components/DocumentNode';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';
import { Document, PaginatedResponse } from '../../types';
import { getDocumentDisplayName } from '../../utils/document';


export const Standard = () => {
  let { type, id } = useParams<{ type: string; id: string }>();
  const { apiUrl } = useEnvironment();
  const [page, setPage] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(false);
  const [err, setErr] = useState<string | Object | null>(null);
  const [data, setData] = useState<PaginatedResponse | null>();

  if (!type) {
    type = 'standard';
  }

  useEffect(() => {
    window.scrollTo(0, 0);
    setLoading(true);
    axios
      .get(`${apiUrl}/${type}/${id}?page=${page}`)
      .then(function (response) {
        setErr(null);
        setData(response.data);
      })
      .catch(function (axiosError) {
        if (axiosError.response.status === 404) {
          setErr('Standard does not exist, please check your search parameters');
        } else {
          setErr(axiosError.response);
        }
      })
      .finally(() => {
        setLoading(false);
      });
  }, [id, type, page]);

  const documents = data?.standards || [];

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
        className="standard-page"
        style={{
          padding: '30px',
          marginTop: 'var(--header-height)',
          marginBottom: 0
        }}
      >
        <h4
          className="standard-page-heading"
          style={{
            fontSize: '2rem',
            marginBottom: 0
          }}
        >
          {id}
        </h4>
        <LoadingAndErrorIndicator loading={loading} error={err} />
        {!loading &&
          !err &&
          documents
            .sort((a, b) => getDocumentDisplayName(a).localeCompare(getDocumentDisplayName(b)))
            .map((standard, i) => (
              <div
                key={i}
                className="standard-page-links-container"
                style={{
                  marginTop: '10px',
                  wordBreak: window.innerWidth < 600 ? 'break-word' : 'normal'
                }}
              >
                <DocumentNode node={standard} linkType={'Standard'} />
              </div>
            ))}
        {renderPagination()}
      </div>
    </>
  );
};
