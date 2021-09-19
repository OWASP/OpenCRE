import React, { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';

import { useEnvironment } from '../../hooks';
import axios from 'axios';
import { DocumentNode } from '../../components/DocumentNode';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { groupBy } from '../../utils/document';
import { Document } from '../../types';

const CRE = "CRE";
const STANDARD = "Standard";

export const SearchName = () => {
  const { searchTerm } = useParams();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect( () => {
    setLoading(true);
    axios.get(`${apiUrl}/text_search`, {params: {text: searchTerm}})
        .then(function (response) {
            setError(null);
            setDocuments(response.data);
        })
        .catch(function (axiosError) {
            // TODO: backend errors if no matches, shoudl return
            //       proper error instead.
            setError(axiosError);
        }).finally( () => {
            setLoading(false);
        });
  }, []);

  const groupedByType = groupBy(documents, doc => doc.doctype);

  const RenderDocuments = ({ documentsToRender}) => {
    return (
        <div>
            {
            documentsToRender.length != 0
            && documentsToRender.map((document, i) => (
                <div key={i} className="accordion ui fluid styled standard-page__links-container">
                    <DocumentNode node={document} linkType={"Standard"}/>
                </div>
            ))}
        </div>
    )
  }

  return (
    <div className="cre-page">
        <h1 className="standard-page__heading">Results matching : <i>{searchTerm}</i></h1>
        <LoadingAndErrorIndicator loading={loading} error={error} />
        { !loading && !error &&
            <div className="ui grid">
                <div className="eight wide column">
                    <h1 className="standard-page__heading">Related CRE's</h1>
                    { groupedByType[CRE] && <RenderDocuments documentsToRender={groupedByType[CRE]}/> }
                </div>
                <div className="eight wide column">
                    <h1 className="standard-page__heading">Related standards</h1>
                    { groupedByType[STANDARD] && <RenderDocuments documentsToRender={groupedByType[STANDARD]}/>}
                </div>
            </div>
        }
    </div>
  );
};
