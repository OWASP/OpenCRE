import axios from 'axios';
import Cookies from 'js-cookie';
import React, { useEffect, useState } from 'react';
import { Button, Checkbox, Form } from 'semantic-ui-react';

const ResourceSelection = ({ onSave }: { onSave: (selectedResources: string[]) => void }) => {
  const [resources, setResources] = useState<string[]>([]);
  const [selectedResources, setSelectedResources] = useState<string[]>([]);

  useEffect(() => {
    const fetchResources = async () => {
      try {
        const response = await axios.get('/api/resources');
        setResources(response.data);
      } catch (error) {
        console.error('Error fetching resources:', error);
      }
    };

    fetchResources();
  }, []);

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
