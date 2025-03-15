// import React, { useState } from 'react';
// import { Button, Checkbox, Form } from 'semantic-ui-react';

// const resources = ['ASVS', 'SAMM', 'ISO', 'NIST'];

// const ResourceSelection = ({ onSave }: { onSave: (selectedResources: string[]) => void }) => {
//   const [selectedResources, setSelectedResources] = useState<string[]>([]);

//   const handleCheckboxChange = (resource: string) => {
//     setSelectedResources((prev) =>
//       prev.includes(resource) ? prev.filter((r) => r !== resource) : [...prev, resource]
//     );
//   };

//   const handleSave = () => {
//     onSave(selectedResources);
//   };

//   return (
//     <Form>
//       {resources.map((resource) => (
//         <Form.Field key={resource}>
//           <Checkbox
//             label={resource}
//             checked={selectedResources.includes(resource)}
//             onChange={() => handleCheckboxChange(resource)}
//           />
//         </Form.Field>
//       ))}
//       <Button onClick={handleSave}>Save</Button>
//     </Form>
//   );
// };

// export default ResourceSelection;

import Cookies from 'js-cookie';
import React, { useState } from 'react';
import { Button, Checkbox, Form } from 'semantic-ui-react';

const resources = ['ASVS', 'SAMM', 'ISO', 'NIST'];

const ResourceSelection = ({ onSave }: { onSave: (selectedResources: string[]) => void }) => {
  const [selectedResources, setSelectedResources] = useState<string[]>([]);

  const handleCheckboxChange = (resource: string) => {
    setSelectedResources((prev) =>
      prev.includes(resource) ? prev.filter((r) => r !== resource) : [...prev, resource]
    );
  };

  const handleSave = () => {
    // Save the selected resources in a cookie
    Cookies.set('selectedResources', JSON.stringify(selectedResources), { expires: 365 });

    // Call the onSave callback with the selected resources
    onSave(selectedResources);
  };

  return (
    <Form>
      {resources.map((resource) => (
        <Form.Field key={resource}>
          <Checkbox
            label={resource}
            checked={selectedResources.includes(resource)}
            onChange={() => handleCheckboxChange(resource)}
          />
        </Form.Field>
      ))}
      <Button onClick={handleSave}>Save</Button>
    </Form>
  );
};

export default ResourceSelection;
