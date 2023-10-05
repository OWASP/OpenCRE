import './standard.scss';

import axios from 'axios';
import React, { useEffect, useState } from 'react';
import { useLocation, useParams } from 'react-router-dom';
import { Pagination } from 'semantic-ui-react';

import { DocumentNode } from '../../components/DocumentNode';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';
import { Document, PaginatedResponse } from '../../types';
import { getDocumentDisplayName } from '../../utils/document';

export const Standard = () => {
  let { type, id } = useParams();
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

  return (
    <>
      <div className="standard-page">
        <h4 className="standard-page__heading">{id}</h4>
        <LoadingAndErrorIndicator loading={loading} error={err} />
        {!loading &&
          !err &&
          documents
            .sort((a, b) => getDocumentDisplayName(a).localeCompare(getDocumentDisplayName(b)))
            .map((standard, i) => (
              <div key={i} className="accordion ui fluid styled standard-page__links-container">
                <DocumentNode node={standard} linkType={'Standard'} />
              </div>
            ))}
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
