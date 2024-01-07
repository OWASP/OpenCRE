import React, { FunctionComponent } from 'react';
import { Icon } from 'semantic-ui-react';

import { Hyperlink } from '../hyper-link/HyperLink';

const HyperlinkIcon: FunctionComponent<Hyperlink> = ({ hyperLink }) => {
  return hyperLink ? (
    <a href={hyperLink} target="_blank">
      <Icon name="external" />
    </a>
  ) : null;
};

export default React.memo(HyperlinkIcon);
