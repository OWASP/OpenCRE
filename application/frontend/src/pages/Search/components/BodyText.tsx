import React, { useState } from 'react';
import { useHistory } from 'react-router-dom';
import { Button, Dropdown, Form, Icon, Input } from 'semantic-ui-react';

import { CRE, STANDARD } from '../../../routes';
import './BodyText.scss';

export const SearchBody = () => {

  return (
    <div className="index-text">
      <h1>
        OPEN CRE
      </h1>
      <p>
        CRE is an interactive content linking platform for uniting security standards and guidelines. It offers easy and robust access to relevant information when designing, developing, testing and procuring secure software.
      </p>

      <h2>
        WHY?
      </h2>
      <p>
        Independent software security professionals got together to find a solution for the complexity and fragmentation in today’s landscape of security standards and guidelines. These people are Spyros Gasteratos, Elie Saad, Rob van der Veer and friends, in close collaboration with the SKF, OpenSSF and Owasp Top 10 project.
      </p>

      <h2>
        HOW?
      </h2>
      <p>
        The CRE links each section of a standard to a shared topic (a Common Requirement), causing that section to also link with all other resources that map to the same topic. This 1) enables users to find all combined information from relevant sources, 2) it facilitates a shared and better understanding of cyber security, and 3) it allows standard makers to have links that keep working and offer all the information that readers need, so they don’t have to cover it all themselves. The CRE maintains itself: topic links in the standard text are scanned automatically. Furthermore, topics are linked with related other topics, creating a semantic web for security.
      </p>
      <p>
      <b>Example</b>: the session time-out topic will take the user to relevant criteria in several standards, and to testing guides, development tips, more technical detail, threat descriptions, articles etc. From there, the user can navigate to resources about session management in general.
      </p>

      <h2>
        WHEN?
      </h2>
      <p>
        CRE is currently in beta and has linked OWASP standards (Top 10, ASVS, Proactive Controls, Cheat sheets, Testing guide), plus several other sources (CWE, NIST-800 53, NIST-800 63b), as part of the
        <a href="https://owasp.org/www-project-integration-standards/"> OWASP Integration standard project</a>
        .
      </p>

      <h2>
        Join us
      </h2>
      <p>
        Contact us (rob.vanderveer@owasp.org) to join the movement. Currently, a stakeholder group is being formed.
      </p>
      <p>
        For more details, see this 
        <a href="https://www.youtube.com/watch?v=MnUR08LOFO0"> introduction video</a>
        , or read the
        <a href="https://github.com/OWASP/www-project-integration-standards/raw/master/writeups/CRE-Explained6.pdf"> CRE explanation document</a>
        .
      </p>

      <h2>
        TRY
      </h2>
      <p>
        See the CRE search bar (beta version). Try searching for
        <a href="/standard/Top10%202017"> Top10 2017 </a>
        as standard and click around, or
        <a href="/cre/482-866"> 482-866 </a>
        as CRE-ID, to get an idea.
      </p>
    </div>
  );
};
