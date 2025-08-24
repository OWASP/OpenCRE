import './search.scss';

import { ArrowDown, Eye, Link2, MessageSquare, Network, Search } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { useToast } from './hooks/use-toast';

export const SearchPage = () => {
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState('');
  const [isArrowVisible, setIsArrowVisible] = useState(true);

  useEffect(() => {
    const handleScroll = () => {
      const footer = document.getElementById('page-footer');
      if (footer) {
        const footerTop = footer.getBoundingClientRect().top;
        const windowHeight = window.innerHeight;
        if (footerTop < windowHeight) {
          setIsArrowVisible(false);
        } else {
          setIsArrowVisible(true);
        }
      }
    };
    window.addEventListener('scroll', handleScroll);
    return () => {
      window.removeEventListener('scroll', handleScroll);
    };
  }, []);

  // The handleSignOut function is no longer needed.

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      toast({
        title: 'Search',
        description: `Searching for: ${searchQuery}`,
      });
    }
  };

  const scrollToNextSection = () => {
    const sections = ['about', 'how-to-use', 'features', 'founders', 'contact', 'community', 'page-footer'];
    const currentScrollY = window.scrollY;
    for (const sectionId of sections) {
      const section = document.getElementById(sectionId);
      if (section) {
        const sectionTop = section.getBoundingClientRect().top + window.scrollY;
        if (sectionTop > currentScrollY + 100) {
          section.scrollIntoView({ behavior: 'smooth' });
          break;
        }
      }
    }
  };

  // The `loading` state is removed, so this block is no longer needed.
  /*
  if (loading) {
    return (
      <div className="loading-container">
        ...
      </div>
    );
  }
  */

  return (
    <div className="main-container">
      {isArrowVisible && (
        <div className="bouncing-arrow">
          <button
            onClick={scrollToNextSection}
            className="bouncing-arrow__button"
            aria-label="Scroll to next section"
            title="Scroll to next section"
          >
            <ArrowDown className="bouncing-arrow__icon" />
          </button>
        </div>
      )}

      {/* The rest of the page remains the same... */}
      <div id="hero" className="hero-section">
        <div className="hero-section__bg-effects">
          <div className="radial-gradient"></div>
          <div className="blur-circle blur-circle--blue"></div>
          <div className="blur-circle blur-circle--purple"></div>
          <div className="blur-circle blur-circle--emerald"></div>
        </div>

        <div className="hero-section__content">
          <div className="hero-section__logo-container">
            <div className="logo-wrapper">
              <img src="/banner.png" alt="OpenCRE - Open Common Requirement Enumeration" />
            </div>
            <p className="logo-subtitle">
              All security standards and guidelines <span>unified</span>
            </p>
          </div>

          <div className="hero-section__description">
            <p>
              OpenCRE is an interactive content linking platform for uniting security standards and
              guidelines. It offers easy navigation between documents, requirements and tools, making it
              easier for developers and security professionals to find the resources they need.
            </p>
          </div>

          <div className="hero-section__search-bar-container">
            <form id="search-bar" onSubmit={handleSearch} className="search-bar">
              <div className="search-bar__group">
                <div className="search-bar__blur-bg"></div>
                <div className="search-bar__wrapper">
                  <div className="search-bar__flex">
                    <Search className="search-bar__icon" />
                    <input
                      type="text"
                      placeholder="Search for security topics ..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="search-bar__input"
                    />
                    <button type="submit" className="search-bar__button">
                      Search
                    </button>
                  </div>
                </div>
              </div>
            </form>
          </div>
        </div>

        <div id="about" className="section">
          <div className="info-card-grid">
            <div className="info-card info-card--blue">
              <h3 className="info-card__title">What is OpenCRE?</h3>
              <p className="info-card__text">
                An <strong>interactive knowledge graph</strong> for security standards and guidelines when
                designing, developing, auditing, testing and procuring for cyber security. It links and
                unlocks these resources into one unified overview.
              </p>
            </div>

            <div className="info-card info-card--emerald">
              <h3 className="info-card__title">How does it work?</h3>
              <p className="info-card__text">
                OpenCRE links each section of a standard to the corresponding{' '}
                <strong>Common Requirement</strong>, causing that section to also link with all other
                standards that link to the same requirement.
              </p>
            </div>

            <div className="info-card info-card--purple">
              <h3 className="info-card__title">Standards unified</h3>
              <div className="info-card__text">
                <p>
                  OpenCRE currently links <strong>OWASP standards</strong> (Top 10, ASVS, Proactive Controls,
                  Cheat sheets, Testing guide, ZAP, Juice shop, SAMM).
                </p>
                <p>
                  Plus several <strong>other sources</strong> (CWE, CAPEC, NIST 800 53, NIST 800 63b, Cloud
                  Control Matrix, ISO27001, ISO27002, and NIST SSDF).
                </p>
              </div>
            </div>
          </div>
        </div>

        <div id="how-to-use" className="section">
          <div className="section__header">
            <h2 className="section__title">HOW TO USE</h2>
            <div className="section__divider section__divider--blue-em-purp"></div>
          </div>
          <div className="how-to-use-grid">
            <div className="htu-card htu-card--orange">
              <div className="htu-card__icon-wrapper">
                <Search className="icon" />
              </div>
              <h3 className="htu-card__title">Lookup Information</h3>
              <div className="htu-card__text">
                <p>
                  Use the{' '}
                  <strong>
                    <a href="#search-bar">search bar</a>
                  </strong>
                  ,{' '}
                  <strong>
                    <a href="/browse">browse</a>
                  </strong>
                  , or{' '}
                  <strong>
                    <a href="/explorer">explore</a>
                  </strong>
                  .
                </p>
                <p>
                  Try the <strong>Top10 2021 page</strong> and click around, or search for "Session".
                </p>
              </div>
            </div>
            <div className="htu-card htu-card--cyan">
              <div className="htu-card__icon-wrapper">
                <Link2 className="icon" />
              </div>
              <h3 className="htu-card__title">Link from your document / tool</h3>
              <p className="htu-card__text">
                Llink with the CRE ID: <a href="https://opencre.org/cre/764-507">opencre.org/cre/764-507</a>{' '}
                or use a familiar standard such as CWE:{' '}
                <a href="https://opencre.org/smartlink/standard/CWE/611">
                  opencre.org/smartlink/standard/CWE/611
                </a>
                .
              </p>
            </div>
            <div className="htu-card htu-card--indigo">
              <div className="htu-card__icon-wrapper">
                <Eye className="icon" />
              </div>
              <h3 className="htu-card__title">Visual Explorer</h3>
              <p className="htu-card__text">
                Check out our{' '}
                <strong>
                  <a href="https://opencre.org/explorer/circles">visual explorer</a>
                </strong>{' '}
                of Common Requirements.
              </p>
            </div>
          </div>
        </div>

        <div id="features" className="section">
          <div className="features-grid">
            <div className="feature-block feature-block--rose">
              <div className="feature-block__icon-wrapper">
                <MessageSquare className="icon" />
              </div>
              <h3 className="feature-block__title">OPENCRE CHAT</h3>
              <p className="feature-block__text">
                Use <strong>OpenCRE Chat</strong> to ask any security question. In collaboration with{' '}
                <strong>Google</strong>, we injected all the standards in OpenCRE into an AI model to create
                the most comprehensive security chatbot. This ensures you get a more{' '}
                <strong>reliable answer</strong>, and also a reference to a <strong>reputable source</strong>.
              </p>
            </div>
            <div className="feature-block feature-block--teal">
              <div className="feature-block__icon-wrapper">
                <Network className="icon" />
              </div>
              <h3 className="feature-block__title">MAP ANALYSIS</h3>
              <p className="feature-block__text">
                Utilize <strong>Map Analysis</strong> as a tool to explore and understand the connections
                between two standards.
              </p>
              <p className="feature-block__text">
                See how <strong>any two standards connect</strong> with each other, providing valuable
                insights.
              </p>
            </div>
          </div>
        </div>

        <div id="founders" className="section">
          <div className="section__header">
            <h2 className="section__title">OUR FOUNDERS</h2>
            <div className="section__divider section__divider--purp-blue-em"></div>
          </div>
          <div className="founders-grid">
            <div className="founders-images">
              <div className="founders-images__row">
                <div className="founder">
                  <div className="founder__img-wrapper">
                    <img alt="Spyros Gasteratos" src="/spyros.jpeg" />
                  </div>
                  <h3 className="founder__name founder__name--spyros">SPYROS GASTERATOS</h3>
                </div>
                <div className="founder">
                  <div className="founder__img-wrapper">
                    <img alt="Rob Van Der Veer" src="/rob.jpeg" />
                  </div>
                  <h3 className="founder__name founder__name--rob">ROB VAN DER VEER</h3>
                </div>
              </div>
            </div>
            <div className="founders-text">
              <div className="text-card">
                <p>
                  OpenCRE is the brainchild of software security professionals{' '}
                  <strong>Spyros Gasteratos</strong> and <strong>Rob van der Veer</strong>, who joined forces
                  to tackle the complexities and segmentation in current security standards and guidelines.
                  They collaborated closely with many initiatives, including <strong>SKF</strong>,{' '}
                  <strong>OpenSSF</strong> and the <strong>Owasp Top10</strong> project.
                </p>
                <p>
                  OpenCRE is an open-source platform overseen by the <strong>OWASP foundation</strong> through
                  the <strong>OWASP Integration standard project</strong>. The goal is to foster better
                  coordination among security initiatives.
                </p>
              </div>
            </div>
          </div>
        </div>

        <div id="contact" className="section">
          <div className="section__header">
            <h2 className="section__title">CONTACT US</h2>
            <div className="section__divider section__divider--blue-em-purp"></div>
          </div>
          <div className="contact-container">
            <div className="contact-card">
              <p className="contact-card__main-text">
                Contact us for any questions, remarks or to join the movement.
              </p>
              <div className="contact-card__info">
                <p className="info-item">
                  <a href="mailto:rob.vanderveer@owasp.org" className="highlight-link">
                    rob.vanderveer[at]owasp.org
                  </a>
                </p>
                <p className="info-item linkedin-text">
                  Follow our <span>LinkedIn page</span>
                </p>
              </div>
              <div className="contact-card__details">
                <p>
                  For more details, see this{' '}
                  <strong>
                    <a href="https://www.youtube.com/watch?v=TwNroVARmB0">interview and demo video</a>
                  </strong>
                  , read the{' '}
                  <strong>
                    <a href="https://github.com/OWASP/www-project-integration-standards/raw/master/writeups/opencredcslides.pdf">
                      OpenCRE slides from the 2023 Appsec conference in Washington DC
                    </a>
                  </strong>
                </p>
              </div>
            </div>
          </div>
        </div>

        <div id="community" className="section">
          <div className="section__header">
            <h2 className="section__title">JOIN OUR COMMUNITY</h2>
            <div className="section__divider section__divider--blue-em-purp"></div>
            <p className="section__description">
              Connect with security professionals, contribute to the project, and stay updated with the latest
              developments.
            </p>
          </div>
          <div className="community-grid">
            <div className="community-card community-card--slack">
              <div className="community-card__icon-wrapper">
                <img
                  src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/slack/slack-original.svg"
                  alt="Slack"
                />
              </div>
              <h3 className="community-card__title">Slack Community</h3>
              <p className="community-card__text">
                Join our active Slack workspace to discuss security topics, ask questions, and collaborate
                with fellow professionals.
              </p>
              <button className="community-card__button">Join Slack</button>
            </div>
            <div className="community-card community-card--linkedin">
              <div className="community-card__icon-wrapper">
                <img
                  src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/linkedin/linkedin-original.svg"
                  alt="LinkedIn"
                />
              </div>
              <h3 className="community-card__title">LinkedIn</h3>
              <p className="community-card__text">
                Follow our LinkedIn page for professional updates, industry insights, and networking
                opportunities.
              </p>
              <button className="community-card__button">Follow Us</button>
            </div>
            <div className="community-card community-card--github">
              <div className="community-card__icon-wrapper">
                <img
                  src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/github/github-original.svg"
                  alt="GitHub"
                />
              </div>
              <h3 className="community-card__title">GitHub</h3>
              <p className="community-card__text">
                Contribute to the open-source project, report issues, and explore the codebase on our GitHub
                repository.
              </p>
              <button className="community-card__button">View Repository</button>
            </div>
          </div>
        </div>

        <footer id="page-footer" className="footer">
          <div className="footer__container">
            <div className="footer__grid">
              <div className="footer__about">
                <Link to="/" className="logo-link">
                  <img src="../logo.svg" alt="Logo" />
                </Link>
                <p>Connecting security standards, requirements, and tools in one comprehensive platform.</p>
              </div>

              <div className="footer__links-column">
                <h4 className="column-title">Standards</h4>
                <div className="links-list">
                  <a href="#">OWASP</a>
                  <a href="#">NIST</a>
                  <a href="#">ISO27001</a>
                  <a href="#">CWE</a>
                </div>
              </div>

              <div className="footer__links-column">
                <h4 className="column-title">Resources</h4>
                <div className="links-list">
                  <a href="#">Documentation</a>
                  <a href="#">API</a>
                  <a href="#">GitHub</a>
                  <a href="#">Contribute</a>
                </div>
              </div>

              <div className="footer__links-column">
                <h4 className="column-title">More Details</h4>
                <div className="links-list">
                  <a href="#">Demo Video</a>
                  <a href="#">Slides OWASP DC</a>
                  <a href="#">OWASP Lisbon talk</a>
                </div>
              </div>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
};

export default SearchPage;
