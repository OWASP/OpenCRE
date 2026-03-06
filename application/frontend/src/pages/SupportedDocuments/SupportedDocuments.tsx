import './SupportedDocuments.scss';

import axios from 'axios';
import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';

type SupportedDocumentsResponse = Record<string, string[]>;

export const SupportedDocuments = () => {
  const { apiUrl } = useEnvironment();
  const [documentsByType, setDocumentsByType] = useState<SupportedDocumentsResponse>({});
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | object | null>(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    window.scrollTo(0, 0);

    axios
      .get(`${apiUrl}/supported_documents`)
      .then((response) => {
        if (!isMounted) return;
        setError(null);
        setDocumentsByType(response.data ?? {});
      })
      .catch((axiosError) => {
        if (!isMounted) return;
        setError(axiosError?.response?.data?.message ?? axiosError.message);
      })
      .finally(() => {
        if (isMounted) {
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [apiUrl]);

  const entries = useMemo(
    () => Object.entries(documentsByType).sort(([left], [right]) => left.localeCompare(right)),
    [documentsByType]
  );

  const total = useMemo(
    () => entries.reduce((sum, [, names]) => sum + names.length, 0),
    [entries]
  );

  const getDocumentPath = (doctype: string, name: string) =>
    `/node/${doctype.toLowerCase()}/${encodeURIComponent(name)}`;

  return (
    <main id="supported-documents">
      <h1>Supported Standards and Documents</h1>
      <p className="supported-documents__summary">
        OpenCRE currently supports {total} unique document sources across {entries.length} document types.
      </p>

      <LoadingAndErrorIndicator loading={loading} error={error} />

      {!loading && !error && (
        <div className="supported-documents__grid">
          {entries.map(([doctype, names]) => (
            <section className="supported-documents__card" key={doctype}>
              <h2>
                {doctype} ({names.length})
              </h2>
              <ul>
                {names.map((name) => (
                  <li key={`${doctype}-${name}`}>
                    <Link to={getDocumentPath(doctype, name)}>{name}</Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </main>
  );
};
