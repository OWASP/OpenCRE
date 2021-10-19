
import React, { useEffect, useState } from 'react';
import { useQuery } from 'react-query';
import { useParams } from 'react-router-dom';
import { useEnvironment } from '../../hooks';
import { Document } from '../../types';

export const Deeplink = () => {
  const { standardName } = useParams();
  const { apiUrl } = useEnvironment();
  
  const { error, data, } = useQuery('deeplink',() => fetch(`${apiUrl}/standard/${standardName}`).then((res) => res.json()),{});


  const documents = data ?.standards || [];
  if (!error){
    for(var standard in documents){
      console.log(standard)
      if ((standard as unknown as Document).hyperlink){
        console.log((standard as unknown as Document).hyperlink)
        window.location.href = (standard as unknown as Document).hyperlink || window.location.href
      }
  }}else{
    console.log(error)
  }
    console.log(documents)
    console.log(error)
    return <div>a</div>;
};
