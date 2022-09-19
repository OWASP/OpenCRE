import React, { useEffect, useState } from 'react';
import { useQuery } from 'react-query';
import { useLocation, useParams } from 'react-router-dom';

import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';
import { Document } from '../../types';

export const Deeplink = () => {
  let { type, nodeName, section, subsection, tooltype } = useParams();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const search = useLocation().search;
  section = section ? section : new URLSearchParams(search).get('section');
  subsection = subsection ? subsection : new URLSearchParams(search).get('subsection');
  tooltype = tooltype ? tooltype : new URLSearchParams(search).get('tooltype');
  if (!type) {
    // Backwards compatible fix, the url used to be /deeplink/:nodename, new url is /deeplink/:type/:nodename
    type = 'Standard';
  }

  var url =
    `${apiUrl}/${type}/${nodeName}` +
    (section != null ? `?section=${section}&` : '') +
    (subsection != null ? `subsection=${subsection}&` : '') +
    (tooltype != null ? `tooltype=${tooltype}&` : '');

  const { error, data, refetch } = useQuery<{ standards: Document[] }, string>(
    'deeplink',
    () => fetch(url).then((res) => res.json()),
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
  }, [type, nodeName]);
  // const { error, data, } = useQuery<{ standards: Document[]; }, string>('deeplink', () => fetch(url).then((res) => res.json()), {});

  const documents = data?.standards || [];
  return (
    <>
      <div className="standard-page">
        <h4 className="standard-page__heading">{nodeName}</h4>
        <LoadingAndErrorIndicator loading={loading} error={error} />
        {!error &&
          !loading &&
          documents.map(
            (standard, i) =>
              // console.log(  (standard && standard.hyperlink && standard.hyperlink.length > 0) ? standard.hyperlink : window.location.href)
              (window.location.href =
                standard && standard.hyperlink && standard.hyperlink.length > 0
                  ? standard.hyperlink
                  : window.location.href)
          )}
      </div>
      ;
    </>
  );
};
