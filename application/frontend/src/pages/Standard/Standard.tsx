import './standard.scss';

import React, { useEffect, useState } from 'react';
import { useQuery } from 'react-query';
import { useLocation, useParams } from 'react-router-dom';
import { Pagination } from 'semantic-ui-react';

import { DocumentNode } from '../../components/DocumentNode';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';
import { Document } from '../../types';

export const Standard = () => {
  let { type, id } = useParams();
  const { apiUrl } = useEnvironment();
  const [page, setPage] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(false);
  if (!type) {
    type = 'standard';
  }
  const { error, data, refetch } = useQuery<
    { standards: Document[]; total_pages: number; page: number },
    string
  >('standard', () => fetch(`${apiUrl}/${type}/${id}?page=${page}`).then((res) => res.json()), {
    retry: false,
    enabled: false,
    onSettled: () => {
      setLoading(false);
    },
  });

  useEffect(() => {
    window.scrollTo(0, 0);
    setLoading(true);
    refetch();
  }, [page, id]);

  const documents = data?.standards || [];

  return (
    <>
      <div className="standard-page">
        <h4 className="standard-page__heading">{id}</h4>
        <LoadingAndErrorIndicator loading={loading} error={error} />
        {!loading &&
          !error &&
          documents.map((standard, i) => (
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
