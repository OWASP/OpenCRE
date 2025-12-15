import React, { Fragment } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';

import { LinkedTreeDocument } from '../../types';

interface LinkedStandardsProps {
  creCode: string;
  linkedTo: LinkedTreeDocument[];
  applyHighlight: (text: string, filter: string) => React.ReactNode;
  filter: string;
}

export const LinkedStandards: React.FC<LinkedStandardsProps> = ({
  creCode,
  linkedTo,
  applyHighlight,
  filter
}) => {
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
    <div style={{ marginLeft: '8px' }}>
      <div
        className="flex gap-1 h-full justify-center items-center flex-wrap"
        style={{ display: 'flex', gap: '4px', alignItems: 'center' }}
      >
        {uniqueLinkedTo.map((x: LinkedTreeDocument) => (
          <Fragment key={x.document.name}>
            {isExternalLink(x, linkedTo) && (
              <a
                href={x.document.hyperlink}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block"
                style={{ textDecoration: 'none' }}
              >
                <span
                  className="inline-flex items-center gap-1 px-2 py-1 text-sm rounded transition-colors"
                  style={{
                    border: '1px solid #2185d0',
                    color: '#2185d0',
                    backgroundColor: '#fff',
                    fontSize: '12px',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = '#4183c4';
                    e.currentTarget.style.color = 'white';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = '#fff';
                    e.currentTarget.style.color = '#2185d0';
                  }}
                >
                  <ExternalLink size={12} />
                  {applyHighlight(x.document.name, filter)}
                </span>
              </a>
            )}
            {!isExternalLink(x, linkedTo) && (
              <Link
                to={getLinkedToUrl(x, creCode)}
                className="inline-block"
                style={{ textDecoration: 'none' }}
              >
                <span
                  className="inline-block px-2 py-1 text-sm rounded transition-colors"
                  style={{
                    border: '1px solid #2185d0',
                    color: '#2185d0',
                    backgroundColor: '#fff',
                    fontSize: '12px',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = '#4183c4';
                    e.currentTarget.style.color = 'white';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = '#fff';
                    e.currentTarget.style.color = '#2185d0';
                  }}
                >
                  {applyHighlight(x.document.name, filter)}
                </span>
              </Link>
            )}
          </Fragment>
        ))}
      </div>
    </div>
  );
};
