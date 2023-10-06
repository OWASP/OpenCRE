import axios from 'axios';
import React, { useEffect, useState } from 'react';
import { useLocation, useParams } from 'react-router-dom';

import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';
import { Document } from '../../types';

export const Deeplink = () => {
  let { type, nodeName, section, subsection, tooltype, sectionID } = useParams();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | Object | null>(null);
  const [data, setData] = useState<Document[] | null>();
  const search = useLocation().search;
  section = section ? section : new URLSearchParams(search).get('section');
  subsection = subsection ? subsection : new URLSearchParams(search).get('subsection');
  tooltype = tooltype ? tooltype : new URLSearchParams(search).get('tooltype');
  sectionID = sectionID ? sectionID : new URLSearchParams(search).get('sectionID');
  if (!type) {
    // Backwards compatible fix, the url used to be /deeplink/:nodename, new url is /deeplink/:type/:nodename
    type = 'Standard';
  }

  var url =
    `${apiUrl}/${type}/${nodeName}` +
    (section != null ? `?section=${section}&` : '') +
    (subsection != null ? `subsection=${subsection}&` : '') +
    (tooltype != null ? `tooltype=${tooltype}&` : '') +
    (sectionID != null ? `sectionID=${sectionID}&` : '');

  useEffect(() => {
    window.scrollTo(0, 0);
    setLoading(true);
    axios
      .get(url)
      .then(function (response) {
        setError(null);
        setData(response.data?.standard);
      })
      .catch(function (axiosError) {
        if (axiosError.response.status === 404) {
          setError('Standard does not exist, please check your search parameters');
        } else {
          setError(axiosError.response);
        }
      })
      .finally(() => {
        setLoading(false);
      });
  }, [type, nodeName]);

  const documents = data || [];
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
