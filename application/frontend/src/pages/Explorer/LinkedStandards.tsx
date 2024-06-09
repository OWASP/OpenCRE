import './LinkedStandards.scss';

import React, { Fragment } from 'react';
import { Link } from 'react-router-dom';
import { Icon, Label, List } from 'semantic-ui-react';

import { LinkedTreeDocument } from '../../types';

export const LinkedStandards = ({ creCode, linkedTo, applyHighlight, filter }) => {
  /**
   * Get a link to a filtered version of the CRE to show the relevant standards
   */
  function getLinkedToUrl(x: LinkedTreeDocument, creCode: string): string {
    return `/cre/${creCode}?applyFilters=true&filters=${x.document.name}&filters=sources`;
  }

  /**
   * Check if this linked document should point to an external address
   * - whether it has other sub-standards with the same name
   * - whether it contains a hyperlink
   * @param x
   * @param linkedTo
   */
  function isExternalLink(x: LinkedTreeDocument, linkedTo: any) {
    if (!x.document.hyperlink) {
      console.log(x.document);
      return false;
    }
    const siblingCount = linkedTo.reduce((count, obj) => {
      count += obj.document.name !== x.document.name ? 0 : 1;
      return count;
    }, 0);
    return siblingCount <= 1;
  }

  /**
   * Avoid repeating tags with the same name
   * @param linkedTo
   */
  function getUniqueByName(linkedTo: any) {
    const seen = new Set();
    return linkedTo.filter((x) => {
      const isDuplicate = seen.has(x.document.name);
      seen.add(x.document.name);
      return !isDuplicate;
    });
  }

  const uniqueLinkedTo = getUniqueByName(linkedTo);

  return (
    <List.Description>
      <Label.Group size="small" className="tags">
        {uniqueLinkedTo.map((x: LinkedTreeDocument) => (
          <Fragment key={x.document.name}>
            {isExternalLink(x, linkedTo) && (
              <a href={x.document.hyperlink} target="_blank">
                <Label>
                  <Icon name="external" />
                  {applyHighlight(x.document.name, filter)}
                </Label>
              </a>
            )}
            {!isExternalLink(x, linkedTo) && (
              <Link to={getLinkedToUrl(x, creCode)}>
                <Label>{applyHighlight(x.document.name, filter)}</Label>
              </Link>
            )}
          </Fragment>
        ))}
      </Label.Group>
    </List.Description>
  );
};
