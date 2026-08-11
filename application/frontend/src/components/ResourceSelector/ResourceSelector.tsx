import React, { useEffect, useState } from 'react';
import { Button, Checkbox, List, Loader, Message } from 'semantic-ui-react';

import { useCapabilities } from '../../hooks/useCapabilities';
import { useEnvironment } from '../../hooks/useEnvironment';
import { useResourceSelection } from '../../hooks/useResourceSelection';
import { useUser } from '../../hooks/useUser';

// Lets a logged-in user pick which standards appear in their account view, and
// persist it (Part of #586). Reuses useUser / useCapabilities / useEnvironment
// and the useResourceSelection hook; renders with semantic-ui-react.
export const ResourceSelector = () => {
  const { apiUrl } = useEnvironment();
  const { capabilities } = useCapabilities();
  const { isLoggedIn, loading: userLoading, login } = useUser();
  const { selected, loading: selectionLoading, saving, error, loadError, save } = useResourceSelection();

  const [standards, setStandards] = useState<string[]>([]);
  const [standardsLoading, setStandardsLoading] = useState(true);
  const [standardsError, setStandardsError] = useState<string | null>(null);
  const [checked, setChecked] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);

  // Fetch the FULL universe of standards. ?all=true bypasses the per-user
  // server-side filter (PR3); without it the picker could only ever show the
  // user's already-selected standards and never offer new ones to add.
  useEffect(() => {
    let active = true;
    fetch(`${apiUrl}/standards?all=true`, { method: 'GET' })
      .then((res) => {
        if (res.status === 200) {
          return res.json();
        }
        throw new Error(`Unexpected /standards status: ${res.status}`);
      })
      .then((data) => {
        if (active && Array.isArray(data)) {
          setStandards(data);
        }
      })
      .catch((err) => {
        if (active) {
          setStandardsError('Could not load the list of standards.');
        }
        console.error('ResourceSelector: could not load standards', err);
      })
      .finally(() => {
        if (active) {
          setStandardsLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [apiUrl]);

  // Initialise the local checkbox state from the saved selection once it loads.
  useEffect(() => {
    setChecked(selected);
  }, [selected]);

  const toggle = (name: string) => {
    setSaved(false);
    setChecked((prev) => (prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]));
  };

  const onSave = async () => {
    setSaved(false);
    const stored = await save(checked);
    if (stored) {
      setSaved(true);
    }
  };

  // Feature gate: this belongs to MyOpenCRE.
  if (capabilities && !capabilities.myopencre) {
    return null;
  }

  // Wait for capabilities and auth state to settle before deciding.
  if (!capabilities || userLoading) {
    return <Loader active inline="centered" content="Loading your standards…" />;
  }

  // Anonymous users can never edit a selection — cover EVERY logged-out case,
  // not only when the login capability is available.
  if (!isLoggedIn) {
    if (capabilities.login) {
      return (
        <Message info>
          <Message.Header>Log in to choose your standards</Message.Header>
          <p>Sign in to pick which standards appear in your OpenCRE view.</p>
          <Button primary onClick={login} content="Login" />
        </Message>
      );
    }
    return <Message info>Choosing your standards requires signing in, which is unavailable here.</Message>;
  }

  // Logged in: wait for the selection and the standards universe to load.
  if (selectionLoading || standardsLoading) {
    return <Loader active inline="centered" content="Loading your standards…" />;
  }

  // If the initial selection load failed we don't know the user's real
  // selection — block editing/Save so an empty list can't overwrite it.
  if (loadError) {
    return <Message negative>Could not load your saved standards. Please refresh and try again.</Message>;
  }

  if (standardsError) {
    return <Message negative>{standardsError}</Message>;
  }

  return (
    <div className="resource-selector">
      <p>Choose which standards appear in your view. OpenCRE is always included.</p>
      {standards.length === 0 ? (
        <Message info>No standards are available yet.</Message>
      ) : (
        <List>
          {standards.map((name) => (
            <List.Item key={name}>
              <Checkbox label={name} checked={checked.includes(name)} onChange={() => toggle(name)} />
            </List.Item>
          ))}
        </List>
      )}
      <Button primary loading={saving} disabled={saving} onClick={onSave} content="Save" />
      {saved && !error && <Message positive>Your standards were saved.</Message>}
      {error && <Message negative>{error}</Message>}
    </div>
  );
};
