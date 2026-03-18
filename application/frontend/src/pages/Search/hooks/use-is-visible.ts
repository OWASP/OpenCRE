import { useState, useEffect, useRef } from 'react';

function useIsVisible() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [isIntersecting, setIsIntersecting] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        // Update state when intersection status changes
        setIsIntersecting(entry.isIntersecting);
      },
      {
        root: null, // observing relative to the document's viewport
        rootMargin: '0px',
        threshold: 0.1, // trigger when 10% of the element is visible
      }
    );

    if (ref.current) {
      observer.observe(ref.current);
    }

    // Cleanup function to unobserve the element when the component unmounts
    return () => {
      if (ref.current) {
        observer.unobserve(ref.current);
      }
    };
  }, []); // Empty dependency array ensures the observer is set up once

  return { ref, isIntersecting };
}

export default useIsVisible;
