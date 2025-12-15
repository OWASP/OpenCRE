import { ArrowDown, Eye, Link2, MessageSquare, Network, Search } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { Link, useHistory } from 'react-router-dom';

import { SEARCH } from '../../const';
import { useToast } from './hooks/use-toast';

export const SearchPage = () => {
  const { toast } = useToast();

  const [isArrowVisible, setIsArrowVisible] = useState(true);

  //Search Functionality
  const history = useHistory();
  const [search, setSearch] = useState({ term: '', error: '' });

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

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (search.term.trim()) {
      toast({
        title: 'Search',
        description: `Searching for: ${search.term}`,
      });
      setSearch({ term: '', error: '' });
      history.push(`${SEARCH}/${search.term}`);
    } else {
      setSearch({
        ...search,
        error: 'Search term cannot be blank',
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

  return (
    <div className="min-h-screen bg-[hsl(222.2,84%,4.9%)] text-[hsl(210,40%,98%)]">
      {/* Bouncing Down Arrow */}
      {isArrowVisible && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50">
          <button
            onClick={scrollToNextSection}
            className="bg-blue-500/20 backdrop-blur-sm border border-blue-400/50 rounded-full p-4 transition-all duration-300 hover:bg-blue-500/30 hover:scale-110 animate-bounce cursor-pointer"
            aria-label="Scroll to next section"
            title="Scroll to next section"
          >
            <ArrowDown className="h-6 w-6 stroke-blue-400" />
          </button>
        </div>
      )}

      {/* Hero Section */}
      <div id="hero" className="min-h-screen bg-gradient-to-br from-[hsl(222.2,84%,4.9%)] to-[hsl(222.2,84%,4.9%)] relative overflow-hidden">
        {/* Background Effects */}
        <div className="absolute inset-0">
          <div className="absolute inset-0 bg-[radial-gradient(circle,rgba(30,58,138,0.2),transparent,transparent)]"></div>
          <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-[48px]"></div>
          <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-[48px]"></div>
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-emerald-500/10 rounded-full blur-[48px]"></div>
        </div>

        {/* Content */}
        <div className="relative z-10 flex flex-col items-center justify-center min-h-screen px-2 mt-12">
          {/* Logo Container */}
          <div className="text-center max-w-[96rem] mx-auto mb-8 animate-[fade-in_0.6s_ease-out]">
            <div className="flex flex-col justify-center mb-12">
              <img src="/banner.png" alt="OpenCRE - Open Common Requirement Enumeration" className="mr-20 h-auto w-full max-w-[64rem]" />
            </div>
            <p className="text-2xl sm:text-2xl md:text-3xl text-[hsl(215,20.2%,65.1%)] max-w-3xl mx-auto leading-relaxed font-semibold">
              All security standards and guidelines <span className="text-blue-400 font-semibold">unified</span>
            </p>
          </div>

          {/* Description */}
          <div className="text-center max-w-5xl mx-auto mb-16 animate-[fade-in_0.6s_ease-out_0.1s]">
            <p className="text-[hsl(215,20.2%,65.1%)] max-w-3xl mx-auto leading-relaxed text-lg sm:text-lg">
              OpenCRE is an interactive content linking platform for uniting security standards and
              guidelines. It offers easy navigation between documents, requirements and tools, making it
              easier for developers and security professionals to find the resources they need.
            </p>
          </div>

          {/* Search Bar Container */}
          <div className="w-full max-w-5xl mx-auto mb-20 animate-[fade-in_0.6s_ease-out_0.2s]">
            <form id="search-bar" onSubmit={handleSearch} className="max-w-2xl mx-auto">
              <div className="relative group">
                {/* Blur background */}
                <div className="absolute inset-0 bg-gradient-to-r from-blue-500/20 via-purple-500/20 to-emerald-500/20 rounded-2xl blur-md group-hover:blur-2xl transition-all"></div>
                
                {/* Search bar wrapper */}
                <div className="relative bg-[hsl(222.2,84%,4.9%)]/60 backdrop-blur-2xl border border-[hsl(217.2,32.6%,17.5%)]/30 rounded-2xl p-2 shadow-2xl">
                  <div className="flex items-center relative">
                    {/* Search Icon */}
                    <Search className="absolute left-6 top-1/2 -translate-y-1/2 text-[hsl(215,20.2%,65.1%)] h-6 w-6 z-10" />
                    
                    {/* Input */}
                    <input
                      type="text"
                      placeholder="Search for security topics ..."
                      value={search.term}
                      onChange={(e) => setSearch({ ...search, term: e.target.value })}
                      className="w-full pl-16 pr-36 py-6 text-lg bg-transparent border-none text-[hsl(210,40%,98%)] focus:outline-none placeholder:text-[hsl(215,20.2%,65.1%)]/70"
                    />
                    
                    {/* Search Button */}
                    <button
                      type="submit"
                      className="absolute right-2 top-1/2 -translate-y-1/2 bg-gradient-to-r from-blue-500 to-blue-600 text-white px-8 py-3 rounded-xl font-medium transition-all duration-200 shadow-lg hover:from-blue-600 hover:to-blue-700 hover:scale-105 border-none cursor-pointer"
                    >
                      Search
                    </button>
                  </div>
                </div>
              </div>
            </form>
          </div>
        </div>

        {/* About Section */}
        <div id="about" className="relative z-10 w-full max-w-[112rem] mx-auto mb-16 px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 animate-[fade-in_0.6s_ease-out_0.4s]">
            {/* What is OpenCRE */}
            <div className="bg-gradient-to-br from-blue-500/20 to-blue-600/30 border border-blue-400/30 backdrop-blur-sm rounded-xl p-6 transition-all duration-300 hover:shadow-[0_20px_25px_-5px_rgba(59,130,246,0.2)] hover:-translate-y-2 hover:from-blue-500/30 hover:to-blue-600/40 hover:border-blue-400/50 text-xl">
              <h3 className="text-2xl font-semibold mb-3 text-blue-300 transition-colors hover:text-blue-200">What is OpenCRE?</h3>
              <p className="text-lg text-[hsl(215,20.2%,65.1%)] leading-relaxed">
                An <strong>interactive knowledge graph</strong> for security standards and guidelines when
                designing, developing, auditing, testing and procuring for cyber security. It links and
                unlocks these resources into one unified overview.
              </p>
            </div>

            {/* How does it work */}
            <div className="bg-gradient-to-br from-emerald-500/20 to-teal-600/30 border border-emerald-400/30 backdrop-blur-sm rounded-xl p-6 transition-all duration-300 hover:shadow-[0_20px_25px_-5px_rgba(16,185,129,0.2)] hover:-translate-y-2 hover:from-emerald-500/30 hover:to-teal-600/40 hover:border-emerald-400/50 text-xl">
              <h3 className="text-2xl font-semibold mb-3 text-emerald-300 transition-colors hover:text-emerald-200">How does it work?</h3>
              <p className="text-lg text-[hsl(215,20.2%,65.1%)] leading-relaxed">
                OpenCRE links each section of a standard to the corresponding{' '}
                <strong>Common Requirement</strong>, causing that section to also link with all other
                standards that link to the same requirement.
              </p>
            </div>

            {/* Standards unified */}
            <div className="bg-gradient-to-br from-purple-500/20 to-pink-600/30 border border-purple-400/30 backdrop-blur-sm rounded-xl p-6 transition-all duration-300 hover:shadow-[0_20px_25px_-5px_rgba(168,85,247,0.2)] hover:-translate-y-2 hover:from-purple-500/30 hover:to-pink-600/40 hover:border-purple-400/50 text-xl">
              <h3 className="text-2xl font-semibold mb-3 text-purple-300 transition-colors hover:text-purple-200">Standards unified</h3>
              <div className="text-lg text-[hsl(215,20.2%,65.1%)] leading-relaxed">
                <p>
                  OpenCRE currently links <strong>OWASP standards</strong> (Top 10, ASVS, Proactive Controls,
                  Cheat sheets, Testing guide, ZAP, Juice shop, SAMM).
                </p>
                <p className="mt-2">
                  Plus several <strong>other sources</strong> (CWE, CAPEC, NIST 800 53, NIST 800 63b, Cloud
                  Control Matrix, ISO27001, ISO27002, and NIST SSDF).
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* How To Use Section */}
        <div id="how-to-use" className="relative z-10 w-full max-w-[112rem] mx-auto mb-16 px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold text-white mb-4">HOW TO USE</h2>
            <div className="w-24 h-1 mx-auto bg-gradient-to-r from-blue-300 via-emerald-300 to-purple-300"></div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {/* Lookup Information */}
            <div className="bg-gradient-to-br from-orange-500/20 to-red-600/30 border border-orange-400/30 backdrop-blur-sm rounded-xl p-8 text-center transition-all duration-300 hover:-translate-y-2 hover:border-orange-400/50 hover:shadow-[0_20px_25px_-5px_rgba(249,115,22,0.2)]">
              <div className="w-16 h-16 bg-gradient-to-br from-orange-500 to-red-500 rounded-full flex items-center justify-center mx-auto mb-6 transition-transform duration-300 hover:scale-110">
                <Search className="h-8 w-8 text-white" />
              </div>
              <h3 className="text-2xl font-semibold mb-4 text-orange-300 transition-colors hover:text-yellow-300">Lookup Information</h3>
              <div className="text-[hsl(215,20.2%,65.1%)] text-lg leading-relaxed mb-4">
                <p>
                  Use the{' '}
                  <strong>
                    <a href="#hero" className="text-orange-300 no-underline hover:text-yellow-300">search bar</a>
                  </strong>
                  ,{' '}
                  <strong>
                    <a href="/root_cres" className="text-orange-300 no-underline hover:text-yellow-300">browse</a>
                  </strong>
                  , or{' '}
                  <strong>
                    <a href="/explorer" className="text-orange-300 no-underline hover:text-yellow-300">explore</a>
                  </strong>
                  .
                </p>
                <p>
                  Try the <strong>Top10 2021 page</strong> and click around, or search for{' '}
                  <strong>Session</strong>.
                </p>
              </div>
            </div>

            {/* Link from your document / tool */}
            <div className="bg-gradient-to-br from-cyan-600/20 to-blue-500/30 border border-cyan-400/30 backdrop-blur-sm rounded-xl p-8 text-center transition-all duration-300 hover:-translate-y-2 hover:border-cyan-400/50 hover:shadow-[0_20px_25px_-5px_rgba(6,182,212,0.2)]">
              <div className="w-16 h-16 bg-gradient-to-br from-cyan-600 to-blue-500 rounded-full flex items-center justify-center mx-auto mb-6 transition-transform duration-300 hover:scale-110">
                <Link2 className="h-8 w-8 text-white" />
              </div>
              <h3 className="text-2xl font-semibold mb-4 text-cyan-300 transition-colors hover:text-cyan-200">Link from your document / tool</h3>
              <p className="text-[hsl(215,20.2%,65.1%)] text-lg leading-relaxed">
                Llink with the CRE ID: <a href="https://opencre.org/cre/764-507" className="text-cyan-300 hover:text-cyan-200">opencre.org/cre/764-507</a>{' '}
                or use a familiar standard such as CWE:{' '}
                <a href="https://opencre.org/smartlink/standard/CWE/611" className="text-cyan-300 hover:text-cyan-200">
                  opencre.org/smartlink/standard/CWE/611
                </a>
                .
              </p>
            </div>

            {/* Visual Explorer */}
            <div className="bg-gradient-to-br from-indigo-500/20 to-purple-500/30 border border-indigo-400/30 backdrop-blur-sm rounded-xl p-8 text-center transition-all duration-300 hover:-translate-y-2 hover:border-indigo-400/50 hover:shadow-[0_20px_25px_-5px_rgba(99,102,241,0.2)]">
              <div className="w-16 h-16 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-full flex items-center justify-center mx-auto mb-6 transition-transform duration-300 hover:scale-110">
                <Eye className="h-8 w-8 text-white" />
              </div>
              <h3 className="text-2xl font-semibold mb-4 text-indigo-300 transition-colors hover:text-indigo-200">Visual Explorer</h3>
              <p className="text-[hsl(215,20.2%,65.1%)] text-lg leading-relaxed">
                Check out our{' '}
                <strong>
                  <a href="https://opencre.org/explorer/circles" className="text-indigo-400 hover:text-indigo-300">visual explorer</a>
                </strong>{' '}
                of Common Requirements.
              </p>
            </div>
          </div>
        </div>

        {/* Features Section */}
        <div id="features" className="relative z-10 w-full max-w-[112rem] mx-auto mb-16 px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
            {/* OpenCRE Chat */}
            <div className="bg-gradient-to-br from-rose-600/20 to-pink-600/30 border border-rose-500/30 backdrop-blur-sm rounded-xl p-8 transition-all duration-300 hover:-translate-y-2 hover:border-rose-500/50 hover:shadow-[0_20px_25px_-5px_rgba(225,29,72,0.2)]">
              <div className="w-16 h-16 bg-gradient-to-br from-rose-600 to-pink-600 rounded-full flex items-center justify-center mb-6 transition-transform duration-300 hover:scale-110">
                <MessageSquare className="h-8 w-8 text-white" />
              </div>
              <h3 className="text-2xl font-semibold mb-4 text-pink-300 transition-colors hover:text-pink-200">OPENCRE CHAT</h3>
              <p className="text-[hsl(215,20.2%,65.1%)] text-lg leading-relaxed mb-4">
                Use{' '}
                <strong>
                  <a href="https://www.opencre.org/chatbot">OpenCRE Chat</a>
                </strong>
                to ask any security question. In collaboration with <strong>Google</strong>, we injected all
                the standards in OpenCRE into an AI model to create the most comprehensive security chatbot.
                This ensures you get a more <strong>reliable answer</strong>, and also a reference to a{' '}
                <strong>reputable source</strong>.
              </p>
            </div>

            {/* Map Analysis */}
            <div className="bg-gradient-to-br from-teal-500/20 to-green-600/30 border border-teal-400/30 backdrop-blur-sm rounded-xl p-8 transition-all duration-300 hover:-translate-y-2 hover:border-teal-400/50 hover:shadow-[0_20px_25px_-5px_rgba(20,184,166,0.2)]">
              <div className="w-16 h-16 bg-gradient-to-br from-teal-500 to-green-600 rounded-full flex items-center justify-center mb-6 transition-transform duration-300 hover:scale-110">
                <Network className="h-8 w-8 text-white" />
              </div>
              <h3 className="text-2xl font-semibold mb-4 text-teal-300 transition-colors hover:text-teal-200">
                <a href="https://www.opencre.org/map_analysis">MAP ANALYSIS</a>
              </h3>
              <p className="text-[hsl(215,20.2%,65.1%)] text-lg leading-relaxed mb-4">
                Utilize <strong><a href="/map_analysis">Map Analysis</a></strong> as a tool to explore and understand the connections
                between two standards.
              </p>
              <p className="text-[hsl(215,20.2%,65.1%)] text-lg leading-relaxed">
                See how <strong>any two standards connect</strong> with each other, providing valuable
                insights.
              </p>
            </div>
          </div>
        </div>

        {/* Founders Section */}
        <div id="founders" className="relative z-10 w-full max-w-[112rem] mx-auto mb-16 px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold text-white mb-4">OUR FOUNDERS</h2>
            <div className="w-24 h-1 mx-auto bg-gradient-to-r from-purple-300 via-blue-300 to-emerald-300"></div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-[0.9fr_1.1fr] gap-6 md:gap-8 items-center">
            {/* Founders Images */}
            <div className="flex flex-col items-center gap-8">
              <div className="flex gap-8">
                <div className="text-center">
                  <div className="w-32 h-32 mx-auto mb-4 transition-transform duration-300 hover:scale-110">
                    <img alt="Spyros Gasteratos" src="/spyros.jpeg" className="w-32 h-32 rounded-full object-cover" />
                  </div>
                  <h3 className="text-xl font-semibold text-white transition-colors hover:text-amber-300">SPYROS GASTERATOS</h3>
                </div>
                <div className="text-center">
                  <div className="w-32 h-32 mx-auto mb-4 transition-transform duration-300 hover:scale-110">
                    <img alt="Rob Van Der Veer" src="/rob.jpeg" className="w-32 h-32 rounded-full object-cover" />
                  </div>
                  <h3 className="text-xl font-semibold text-white transition-colors hover:text-violet-300">ROB VAN DER VEER</h3>
                </div>
              </div>
            </div>

            {/* Founders Text */}
            <div className="flex flex-col gap-6 text-lg">
              <div className="bg-gradient-to-br from-gray-500/20 to-gray-600/30 border border-gray-400/30 backdrop-blur-sm rounded-xl p-6 transition-all duration-300 hover:-translate-y-2 hover:border-gray-400/50 hover:shadow-[0_20px_25px_-5px_rgba(107,114,128,0.2)] hover:from-gray-500/30 hover:to-gray-600/40">
                <p className="text-[hsl(215,20.2%,65.1%)] leading-relaxed mb-4">
                  OpenCRE is the brainchild of software security professionals{' '}
                  <strong>Spyros Gasteratos</strong> and <strong>Rob van der Veer</strong>, who joined forces
                  to tackle the complexities and segmentation in current security standards and guidelines.
                  They collaborated closely with many initiatives, including <strong>SKF</strong>,{' '}
                  <strong>OpenSSF</strong> and the <strong>Owasp Top10</strong> project.
                </p>
                <p className="text-[hsl(215,20.2%,65.1%)] leading-relaxed">
                  OpenCRE is an open-source platform overseen by the <strong>OWASP foundation</strong> through
                  the <strong>OWASP Integration standard project</strong>. The goal is to foster better
                  coordination among security initiatives.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Contact Section */}
        <div id="contact" className="relative z-10 w-full max-w-[112rem] mx-auto mb-16 px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold text-white mb-4">CONTACT US</h2>
            <div className="w-24 h-1 mx-auto bg-gradient-to-r from-blue-300 via-emerald-300 to-purple-300"></div>
          </div>
          <div className="max-w-4xl mx-auto">
            <div className="bg-gradient-to-br from-blue-500/20 to-indigo-600/30 border border-blue-400/30 backdrop-blur-sm rounded-xl p-8 text-center transition-all duration-300 hover:-translate-y-2 hover:border-blue-400/50 hover:shadow-[0_20px_25px_-5px_rgba(59,130,246,0.2)] hover:from-blue-500/30 hover:to-indigo-600/40">
              <p className="text-[hsl(215,20.2%,65.1%)] leading-relaxed mb-6 text-lg">
                Contact us for any questions, remarks or to join the movement.
              </p>
              <div className="mb-8 text-lg">
                <p className="text-lg mb-4">
                  <a href="mailto:rob.vanderveer@owasp.org" className="text-blue-300 font-semibold underline hover:text-blue-200">
                    rob.vanderveer[at]owasp.org
                  </a>
                </p>
                <p className="text-lg">
                  Follow our{' '}
                  <span className="text-blue-300 hover:text-blue-200">
                    <a href="https://www.linkedin.com/company/opencre/posts/?feedView=all">LinkedIn page</a>
                  </span>
                </p>
              </div>
              <div className="bg-blue-500/20 rounded-lg p-6 transition-colors hover:bg-blue-500/30">
                <p className="text-[hsl(215,20.2%,65.1%)] text-lg leading-relaxed">
                  For more details, see this{' '}
                  <strong>
                    <a href="https://www.youtube.com/watch?v=TwNroVARmB0" className="text-blue-300 hover:text-blue-200">interview and demo video</a>
                  </strong>
                  , read the{' '}
                  <strong>
                    <a href="https://github.com/OWASP/www-project-integration-standards/raw/master/writeups/opencredcslides.pdf" className="text-blue-300 hover:text-blue-200">
                      OpenCRE slides from the 2023 Appsec conference in Washington DC
                    </a>
                  </strong>
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Community Section */}
        <div id="community" className="relative z-10 w-full max-w-[112rem] mx-auto mb-16 px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold text-white mb-4">JOIN OUR COMMUNITY</h2>
            <div className="w-24 h-1 mx-auto bg-gradient-to-r from-blue-300 via-emerald-300 to-purple-300"></div>
            <p className="text-[hsl(215,20.2%,65.1%)] text-lg max-w-2xl mx-auto mt-6 leading-relaxed">
              Connect with security professionals, contribute to the project, and stay updated with the latest
              developments.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {/* Slack Community */}
            <div className="bg-gradient-to-br from-purple-500/20 to-pink-600/30 border border-purple-400/30 backdrop-blur-sm rounded-xl p-8 text-center transition-all duration-300 hover:-translate-y-2 hover:border-purple-400/50 hover:shadow-[0_20px_25px_-5px_rgba(168,85,247,0.2)]">
              <div className="w-20 h-20 bg-white rounded-2xl flex items-center justify-center mx-auto mb-6 transition-transform duration-300 hover:scale-110">
                <img
                  src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/slack/slack-original.svg"
                  alt="Slack"
                  className="h-12 w-12"
                />
              </div>
              <h3 className="text-2xl font-semibold mb-4 text-purple-300 transition-colors hover:text-purple-200">Slack Community</h3>
              <p className="text-[hsl(215,20.2%,65.1%)] text-lg leading-relaxed mb-6">
                Join our active Slack workspace to discuss security topics, ask questions, and collaborate
                with fellow professionals.
              </p>
              <a href="https://owasp.org/slack/invite">
                <button className="border border-purple-400 text-purple-400 bg-transparent px-4 py-2 rounded-md transition-all duration-200 hover:bg-purple-400/10 hover:text-purple-200 cursor-pointer">Join Slack</button>
              </a>
            </div>

            {/* LinkedIn */}
            <div className="bg-gradient-to-br from-blue-500/20 to-cyan-600/30 border border-blue-400/30 backdrop-blur-sm rounded-xl p-8 text-center transition-all duration-300 hover:-translate-y-2 hover:border-blue-400/50 hover:shadow-[0_20px_25px_-5px_rgba(59,130,246,0.2)]">
              <div className="w-20 h-20 bg-white rounded-2xl flex items-center justify-center mx-auto mb-6 transition-transform duration-300 hover:scale-110">
                <img
                  src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/linkedin/linkedin-original.svg"
                  alt="LinkedIn"
                  className="h-12 w-12"
                />
              </div>
              <h3 className="text-2xl font-semibold mb-4 text-blue-300 transition-colors hover:text-blue-200">LinkedIn</h3>
              <p className="text-[hsl(215,20.2%,65.1%)] text-lg leading-relaxed mb-6">
                Follow our LinkedIn page for professional updates, industry insights, and networking
                opportunities.
              </p>
              <a href="https://www.linkedin.com/company/opencre/posts/?feedView=all">
                <button className="border border-blue-400 text-blue-400 bg-transparent px-4 py-2 rounded-md transition-all duration-200 hover:bg-blue-400/10 hover:text-blue-300 cursor-pointer">Follow Us</button>
              </a>
            </div>

            {/* GitHub */}
            <div className="bg-gradient-to-br from-gray-500/20 to-gray-600/30 border border-gray-400/30 backdrop-blur-sm rounded-xl p-8 text-center transition-all duration-300 hover:-translate-y-2 hover:border-gray-400/50 hover:shadow-[0_20px_25px_-5px_rgba(107,114,128,0.2)]">
              <div className="w-20 h-20 bg-white rounded-2xl flex items-center justify-center mx-auto mb-6 transition-transform duration-300 hover:scale-110">
                <img
                  src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/github/github-original.svg"
                  alt="GitHub"
                  className="h-12 w-12"
                />
              </div>
              <h3 className="text-2xl font-semibold mb-4 text-gray-300 transition-colors hover:text-gray-200">GitHub</h3>
              <p className="text-[hsl(215,20.2%,65.1%)] text-lg leading-relaxed mb-6">
                Contribute to the open-source project, report issues, and explore the codebase on our GitHub
                repository.
              </p>
              <a href="https://github.com/OWASP/OpenCRE">
                <button className="border border-gray-400 text-gray-400 bg-transparent px-4 py-2 rounded-md transition-all duration-200 hover:bg-gray-400/10 hover:text-gray-300 cursor-pointer">View Repository</button>
              </a>
            </div>
          </div>
        </div>

        {/* Footer */}
        <footer id="page-footer" className="relative z-10 w-full border-t border-[hsl(217.2,32.6%,17.5%)]/50 pt-12 pb-12 backdrop-blur-sm">
          <div className="max-w-[112rem] mx-auto px-4 sm:px-6 lg:px-8">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
              {/* About */}
              <div className="flex flex-col gap-4">
                <Link to="/" className="flex items-center gap-2">
                  <img src="../logo.svg" alt="Logo" className="h-40 w-40" />
                </Link>
                <p className="text-[hsl(215,20.2%,65.1%)]">Connecting security standards, requirements, and tools in one comprehensive platform.</p>
              </div>

              {/* Standards */}
              <div>
                <h4 className="text-white font-medium mb-4">Standards</h4>
                <div className="flex flex-col gap-2">
                  <a href="https://owasp.org/" className="block text-[hsl(215,20.2%,65.1%)] transition-colors hover:text-[hsl(210,40%,98%)] no-underline">OWASP</a>
                  <a href="https://opencre.org/node/standard/NIST%20800-53%20v5/section/" className="block text-[hsl(215,20.2%,65.1%)] transition-colors hover:text-[hsl(210,40%,98%)] no-underline">NIST</a>
                  <a href="https://opencre.org/node/standard/ISO%2027001/section/" className="block text-[hsl(215,20.2%,65.1%)] transition-colors hover:text-[hsl(210,40%,98%)] no-underline">ISO27001</a>
                  <a href="https://opencre.org/node/standard/CWE/" className="block text-[hsl(215,20.2%,65.1%)] transition-colors hover:text-[hsl(210,40%,98%)] no-underline">CWE</a>
                </div>
              </div>

              {/* Resources */}
              <div>
                <h4 className="text-white font-medium mb-4">Resources</h4>
                <div className="flex flex-col gap-2">
                  <a href="https://github.com/OWASP/OpenCRE/blob/main/README.md" className="block text-[hsl(215,20.2%,65.1%)] transition-colors hover:text-[hsl(210,40%,98%)] no-underline">Documentation</a>
                  <a href="https://github.com/OWASP/OpenCRE/blob/main/docs/my-opencre-user-guide.md" className="block text-[hsl(215,20.2%,65.1%)] transition-colors hover:text-[hsl(210,40%,98%)] no-underline">API</a>
                  <a href="https://github.com/OWASP/OpenCRE/" className="block text-[hsl(215,20.2%,65.1%)] transition-colors hover:text-[hsl(210,40%,98%)] no-underline">GitHub</a>
                  <a href="https://github.com/OWASP/OpenCRE/blob/main/docs/CONTRIBUTING.md" className="block text-[hsl(215,20.2%,65.1%)] transition-colors hover:text-[hsl(210,40%,98%)] no-underline">Contribute</a>
                </div>
              </div>

              {/* More Details */}
              <div>
                <h4 className="text-white font-medium mb-4">More Details</h4>
                <div className="flex flex-col gap-2">
                  <a href="https://www.youtube.com/watch?v=TwNroVARmB0" className="block text-[hsl(215,20.2%,65.1%)] transition-colors hover:text-[hsl(210,40%,98%)] no-underline">Demo Video</a>
                  <a href="https://github.com/OWASP/www-project-integration-standards/raw/master/writeups/opencredcslides.pdf" className="block text-[hsl(215,20.2%,65.1%)] transition-colors hover:text-[hsl(210,40%,98%)] no-underline">
                    Slides OWASP DC
                  </a>
                  <a href="https://www.youtube.com/watch?v=Uhg1dtzwSKM&pp=ygUNb3dhc3Agb3BlbmNyZQ%3D%3D" className="block text-[hsl(215,20.2%,65.1%)] transition-colors hover:text-[hsl(210,40%,98%)] no-underline">
                    OWASP Lisbon talk 
                  </a>
                </div>
              </div>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
};


