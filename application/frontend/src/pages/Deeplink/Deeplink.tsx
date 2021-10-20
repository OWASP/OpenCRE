
import React, { useEffect, useState } from 'react';
import { useQuery } from 'react-query';
import { useParams, useLocation } from 'react-router-dom';
import { useEnvironment } from '../../hooks';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { Document } from '../../types';

export const Deeplink = () => {
  const { standardName } = useParams();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const search = useLocation().search;
  const section = new URLSearchParams(search).get('section')
  const subsection = new URLSearchParams(search).get('subsection')
  var url = `${apiUrl}/standard/${standardName}`  + (section != null? `?section=${section}&`:"") + (subsection !=null? `subsection=${subsection}&`:"")
  const { error, data, } = useQuery<{ standards: Document[]; }, string>('deeplink', () => fetch(url).then((res) => res.json()), {});


  const documents = data?.standards || [];
  return (<>
      <div className="standard-page">
        <h4 className="standard-page__heading">{standardName}</h4>
        <LoadingAndErrorIndicator loading={loading} error={error} />
            {!error && 
              !loading &&
              documents.map((standard, i) => (
                window.location.href = ( standard && standard.hyperlink && standard.hyperlink.length > 0 ) ? standard.hyperlink : window.location.href

          ))}
          </div>;
      </>
      );
  
 
};
