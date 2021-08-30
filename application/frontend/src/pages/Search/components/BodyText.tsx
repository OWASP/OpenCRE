import React, { useState } from 'react';
import { useHistory } from 'react-router-dom';
import { Button, Dropdown, Form, Icon, Input } from 'semantic-ui-react';

import { CRE, STANDARD } from '../../../routes';
import './BodyText.scss';

export const SearchBody = () => {

  return (
    <div className="index-text">
      <h1>OPEN CRE</h1>
Linking standards. By the community, for the community.
Open Common Requirement Enumeration links standards and guidelines at the level of topics that need to be taken into account when procuring, designing, building and testing great software.
      <h2>WHY?</h2>
<p>CRE follows up on the ENISA recommendation for a repository to bring the fragmented landscape of security knowledge resources together.
This initiative was taken by an independent group of software security experts who got together to make it 1) easier to create and maintain standards and guidelines, and 2) easier to find relevant information.
No more endless searches for relevant rules and information, no more broken links, no more need to cover every topic everywhere - just link.
</p>
   <h2>WHAT?</h2>
<p>The idea of CRE is to link each section of a resource to a shared topic identifier (a Common Requirement), instead of linking to just 1 or 2 other resources. Through this shared link, all resources map to eachother. This 1) enables standard and guideline makers to work efficiently, 2) it enables users to find the information they need, and 3) it facilitates a shared understanding in the industry of what cyber security is. The key element is self-maintainability: the CRE topic links in the resource can be automatically parsed and used to map everything together. No more manual mapping labour. Furthermore, because the topics are linked as well, users can quickly find more relevant material through related topics.
For example the topic of session time-out will take the user not only to relevant criteria in several standards, but also to testing guides, development tips, more technical detail, threat descriptions, articles etc. Plus, from there the user can navigate to resources about session management in general.
The CRE only links and therefore does not create a new standard of requirements. It is simply a standard on how standards can link together.
</p>   <h2>WHEN?</h2>
<p>Currently, CRE has linked several OWASP standards together, and included other standards (CWE, NIST-800 53, NIST-800 63b), as part of the OWASP Integration standard project.
Join the movement.</p>
    </div>
  );
};
