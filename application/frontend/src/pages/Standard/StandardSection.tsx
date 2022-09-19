import './standard.scss';

import React, { useEffect, useMemo, useState } from 'react';
import { useQuery } from 'react-query';
import { useParams } from 'react-router-dom';
import { Pagination } from 'semantic-ui-react';

import { DocumentNode } from '../../components/DocumentNode';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { DOCUMENT_TYPE_NAMES } from '../../const';
import { useEnvironment } from '../../hooks';
import { Document } from '../../types';
import { groupLinksByType } from '../../utils';

export const StandardSection = () => {
  const { id, section } = useParams();
  const { apiUrl } = useEnvironment();
  const [page, setPage] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(false);

  const getSectionParameter = (): string => {
    return section ? `&section=${encodeURIComponent(section)}` : '';
  };

  const { error, data, refetch } = useQuery<
    { standards: Document[]; total_pages: number; page: number },
    string
  >(
    'standard section',
    () => fetch(`${apiUrl}/standard/${id}?page=${page}${getSectionParameter()}`).then((res) => res.json()),
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
  }, [page, id]);

  const documents = data?.standards || [];
  const document = documents[0];
  const linksByType = useMemo(() => (document ? groupLinksByType(document) : {}), [document]);

  return (
    <>
      <div className="standard-page section-page">
        <h4 className="standard-page__heading">{id}</h4>
        <h5 className="standard-page__sub-heading">Section: {document?.section}</h5>
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
            {Object.keys(linksByType).length > 0 &&
              Object.entries(linksByType).map(([type, links]) => (
                <div className="cre-page__links" key={type}>
                  <div className="cre-page__links-header">
                    {document.doctype}: {document.name} - {document.section}{' '}
                    <b>{DOCUMENT_TYPE_NAMES[type]}</b>:
                  </div>
                  {links.map((link, i) => (
                    <div key={i} className="accordion ui fluid styled cre-page__links-container">
                      <DocumentNode node={link.document} linkType={type} />
                    </div>
                  ))}
                </div>
              ))}
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
