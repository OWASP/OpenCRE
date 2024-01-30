import React, { FunctionComponent } from 'react';

export interface Hyperlink {
  hyperLink?: string;
}

const Hyperlink: FunctionComponent<Hyperlink> = ({ hyperLink }) => {
  return hyperLink ? (
    <>
      <span>Reference:</span>
      <a href={hyperLink} target="_blank">
        {' '}
        {hyperLink}
      </a>
    </>
  ) : null;
};

export default React.memo(Hyperlink);
