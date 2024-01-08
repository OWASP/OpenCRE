import axios from 'axios';
import React, { useEffect, useState } from 'react';
import { useLocation, useParams } from 'react-router-dom';

import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';
import { Document } from '../../types';
import { Standard } from '../Standard/Standard';

export const Deeplink = () => {
  let { type, nodeName, section, subsection, tooltype, sectionID, sectionid } = useParams();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | Object | null>(null);
  const [data, setData] = useState<Document[] | null>();
  const search = useLocation().search;
  section = section ? section : new URLSearchParams(search).get('section');
  subsection = subsection ? subsection : new URLSearchParams(search).get('subsection');
  tooltype = tooltype ? tooltype : new URLSearchParams(search).get('tooltype');
  sectionID = sectionID ? sectionID : new URLSearchParams(search).get('sectionID');
  sectionid = sectionID ? sectionID : new URLSearchParams(search).get('sectionid');
  if (!type) {
    // Backwards compatible fix, the url used to be /deeplink/:nodename, new url is /deeplink/:type/:nodename
    type = 'Standard';
  }

  var apiCall = new URL(`${apiUrl}/${type}/${nodeName}?`);

  if (section != null) {
    apiCall.searchParams.append('section', section);
  }
  if (subsection != null) {
    apiCall.searchParams.append('subsection', subsection);
  }
  if (tooltype != null) {
    apiCall.searchParams.append('tooltype', tooltype);
  }
  if (sectionID != null) {
    apiCall.searchParams.append('sectionID', sectionID);
  } else if (sectionid != null) {
    apiCall.searchParams.append('sectionID', sectionid);
  }
  useEffect(() => {
    window.scrollTo(0, 0);
    setLoading(true);
    axios
      .get(apiCall.toString())
      .then(function (response) {
        setError(null);
        setData(response.data?.standards);
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

  var redirectTo = window.location.href;
  if (documents) {
    for (const standard of documents) {
      if (standard.hyperlink && standard.hyperlink?.length > 0) {
        redirectTo = standard.hyperlink;
      }
    }
  }
  if (!error && !loading && redirectTo != window.location.href) {
    return (
      <div className="standard-page">
        <h4 className="standard-page__heading">{nodeName}</h4>
        <LoadingAndErrorIndicator loading={loading} error={error} />
        <h4>Redirecting to:</h4>
        {window.location.href}
        {(window.location.href = redirectTo)}
      </div>
    );
  } else {
    return (
      <div className="standard-page">
        <h4 className="standard-page__heading">{nodeName}</h4>
        <LoadingAndErrorIndicator loading={loading} error={error} />
      </div>
    );
  }
};
