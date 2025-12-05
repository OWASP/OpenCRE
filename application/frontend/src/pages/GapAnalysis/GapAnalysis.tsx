import axios from 'axios';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { ArrowDown, ArrowUp, Share2, Info, Loader2, XCircle, CheckCircle } from 'lucide-react';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { GA_STRONG_UPPER_LIMIT } from '../../const';
import { useEnvironment } from '../../hooks';
import { GapAnalysisPathStart } from '../../types';
import { getDocumentDisplayName } from '../../utils';
import { getInternalUrl } from '../../utils/document';


const GetSegmentText = (segment: any, segmentID: string) => {
  let textPart = segment.end;
  let nextID = segment.end.id;
  let ArrowIcon = <ArrowDown className="inline w-3 h-3 align-middle" />;
  if (segmentID !== segment.start.id) {
    textPart = segment.start;
    nextID = segment.start.id;
    ArrowIcon = <ArrowUp className="inline w-3 h-3 align-middle" />;
  }
  const text = (
    <>
      <br />
      {ArrowIcon}{' '}
      <span className="capitalize">
        {segment.relationship.replace('_', ' ').toLowerCase()} {segment.score > 0 && <> (+{segment.score})</>}
      </span>
      <br />
      <span className="font-medium">{getDocumentDisplayName(textPart, true)}</span>{' '}
      {textPart.section ?? ''} {textPart.subsection ?? ''} {textPart.description ?? ''}
    </>
  );
  return { text, nextID };
};

function useQuery() {
  const { search } = useLocation();
  return React.useMemo(() => new URLSearchParams(search), [search]);
}

const GetStrength = (score: number) => {
  if (score == 0) return 'Direct';
  if (score <= GA_STRONG_UPPER_LIMIT) return 'Strong';
  if (score >= 20) return 'Weak';
  return 'Average';
};

const GetStrengthColor = (score: number) => {
  if (score === 0) return 'text-green-700';
  if (score <= GA_STRONG_UPPER_LIMIT) return 'text-lime-600';
  if (score >= 20) return 'text-red-600';
  return 'text-amber-500';
};

type DropdownItemProps = {
  key: string;
  text: string;
  value: string | undefined;
};

const Tooltip = ({ trigger, content, wide = false }: { trigger: React.ReactNode; content: React.ReactNode; wide?: boolean }) => {
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [ref]);

  const contentClasses = `absolute z-50 p-3 bg-white border border-gray-300 rounded-lg shadow-xl text-sm ${wide ? 'w-80' : 'w-64'
    } top-full mt-2 left-1/2 transform -translate-x-1/2 transition-opacity duration-300 ${isOpen ? 'opacity-100 visible' : 'opacity-0 invisible'
    }`;

  return (
    <div
      ref={ref}
      className="relative inline-block"
      onMouseEnter={() => setIsOpen(true)}
      onMouseLeave={() => setIsOpen(false)}
    >
      {trigger}
      <div className={contentClasses}>
        <div className="text-center">{content}</div>
      </div>
    </div>
  );
};


const GetResultLine = (path: any, gapAnalysis: Record<string, GapAnalysisPathStart>, key: string) => {
  let segmentID = gapAnalysis[key].start.id;
  const strengthColor = GetStrengthColor(path.score);

  const pathContent = (
    <>
      <span className="font-bold">{getDocumentDisplayName(gapAnalysis[key].start, true)}</span>
      {path.path.map((segment: any) => {
        const { text, nextID } = GetSegmentText(segment, segmentID);
        segmentID = nextID;
        return text;
      })}
    </>
  );

  const scoreContent = (
    <>
      <b className="block mb-1">Generally: lower is better</b>
      <div className="text-left space-y-1">
        <b className={GetStrengthColor(0)}>{GetStrength(0)} (0)</b>: Directly Linked
        <br />
        <b className={GetStrengthColor(GA_STRONG_UPPER_LIMIT)}>{GetStrength(GA_STRONG_UPPER_LIMIT)} ($\leq{GA_STRONG_UPPER_LIMIT}$)</b>: Closely connected likely to have majority overlap
        <br />
        <b className={GetStrengthColor(6)}>{GetStrength(6)} (6)</b>: Connected likely to have partial overlap
        <br />
        <b className={GetStrengthColor(22)}>{GetStrength(22)} (22)</b>: Weakly connected likely to have small or no overlap
      </div>
    </>
  );

  return (
    <div key={path.end.id} className="mb-1 font-bold">
      <a
        href={getInternalUrl(path.end)}
        target="_blank"
        rel="noopener noreferrer"
        className="text-blue-600 hover:text-blue-800 transition duration-150"
      >
        <Tooltip
          wide={true}
          trigger={<span className="hover:underline cursor-pointer">{getDocumentDisplayName(path.end, true)} </span>}
          content={pathContent}
        />

        <Tooltip
          trigger={
            <b className={`${strengthColor} hover:text-black cursor-pointer transition duration-150`}>
              ({GetStrength(path.score)}:{path.score})
            </b>
          }
          content={scoreContent}
        />
      </a>
    </div>
  );
};


export const GapAnalysis = () => {
  const standardOptionsDefault: DropdownItemProps[] = [{ key: 'default', text: 'Select Standard', value: undefined }];
  const searchParams = useQuery();
  const [standardOptions, setStandardOptions] = useState<DropdownItemProps[] | undefined>(
    standardOptionsDefault
  );
  const [BaseStandard, setBaseStandard] = useState<string | undefined>(searchParams.get('base') ?? '');
  const [CompareStandard, setCompareStandard] = useState<string | undefined>(
    searchParams.get('compare') ?? ''
  );
  const [gaJob, setgaJob] = useState<string>('');
  const [gapAnalysis, setGapAnalysis] = useState<Record<string, GapAnalysisPathStart>>();
  const [loadingStandards, setLoadingStandards] = useState<boolean>(false);
  const [loadingGA, setLoadingGA] = useState<boolean>(false);
  const [error, setError] = useState<string | null | object>(null);
  const { apiUrl } = useEnvironment();
  const timerIdRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    const fetchData = async () => {
      const result = await axios.get(`${apiUrl}/standards`);
      setLoadingStandards(false);
      setStandardOptions(
        standardOptionsDefault.concat(result.data.sort().map((x: string) => ({ key: x, text: x, value: x })))
      );
    };

    setLoadingStandards(true);
    fetchData().catch((e) => {
      setLoadingStandards(false);
      setError((e.response?.data?.message as string) ?? e.message);
    });
  }, [setStandardOptions, setLoadingStandards, setError]);

  useEffect(() => {
    const pollingCallback = () => {
      const fetchData = async () => {
        const result = await axios.get(`${apiUrl}/ma_job_results?id=` + gaJob, {
          headers: {
            'Cache-Control': 'no-cache',
            Pragma: 'no-cache',
            Expires: '0',
          },
        });
        if (result.data.result) {
          setLoadingGA(false);
          setGapAnalysis(result.data.result);
          setgaJob(''); // Clears job ID on success to stop polling
        }
      };
      if (!gaJob) return;
      fetchData().catch((e) => {
        setLoadingGA(false);
        setError((e.response?.data?.message as string) ?? e.message);
        // ⭐ IMPORTANT FIX: Clear the job ID on polling failure to stop the interval
        setgaJob('');
      });
    };

    const startPolling = () => {
      if (timerIdRef.current === undefined) {
        timerIdRef.current = setInterval(pollingCallback, 10000) as unknown as number;
      }
    };

    const stopPolling = () => {
      if (timerIdRef.current !== undefined) {
        clearInterval(timerIdRef.current);
        timerIdRef.current = undefined;
      }
    };

    if (gaJob) {
      console.log('started polling');
      startPolling();
    } else {
      console.log('stoped polling');
      stopPolling();
    }

    return () => {
      stopPolling();
    };
  }, [gaJob]);

  useEffect(() => {
    const fetchData = async () => {
      const result = await axios.get(
        `${apiUrl}/map_analysis?standard=${BaseStandard}&standard=${CompareStandard}`
      );
      if (result.data.result) {
        setLoadingGA(false);
        setGapAnalysis(result.data.result);
      } else if (result.data.job_id) {
        setgaJob(result.data.job_id);
        // Note: loadingGA remains true here, expecting polling to clear it.
      } else {
        // ⭐ OPTIONAL FIX: Handle unexpected API response that has neither result nor job_id.
        console.error("API response missing result or job_id.");
        setError("Analysis request failed to start correctly.");
        setLoadingGA(false);
      }
    };

    if (!BaseStandard || !CompareStandard || BaseStandard === CompareStandard) return;
    setGapAnalysis(undefined);
    setError(null); // Clear any previous error before starting new analysis
    setLoadingGA(true);
    fetchData().catch((e) => {
      setLoadingGA(false);
      setError((e.response?.data?.message as string) ?? e.message);
    });
  }, [BaseStandard, CompareStandard, setGapAnalysis, setLoadingGA, setError]);
  // ... rest of the component is unchanged

  const getWeakLinks = useCallback(
    async (key: string) => {
      if (!gapAnalysis) return;
      try {
        const result = await axios.get(
          `${apiUrl}/map_analysis_weak_links?standard=${BaseStandard}&standard=${CompareStandard}&key=${key}`
        );
        if (result.data.result) {
          setGapAnalysis((prevGapAnalysis) => {
            if (!prevGapAnalysis) return undefined;
            const newGapAnalysis = { ...prevGapAnalysis };
            newGapAnalysis[key] = {
              ...newGapAnalysis[key],
              weakLinks: result.data.result.paths,
            };
            return newGapAnalysis;
          });
        }
      } catch (e: any) {
        setError(e.response?.data?.message ?? e.message);
      }
    },
    [gapAnalysis, BaseStandard, CompareStandard, apiUrl]
  );

  const StandardDropdown = ({
    placeholder,
    options,
    value,
    onChange,
    disabled = false
  }: {
    placeholder: string;
    options: DropdownItemProps[] | undefined;
    value: string | undefined;
    onChange: (value: string | undefined) => void;
    disabled?: boolean;
  }) => {
    return (
      <select
        className="w-full md:w-auto p-2 border border-gray-300 rounded-md shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-sm disabled:bg-gray-50"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || undefined)}
        disabled={disabled}
      >
        {options?.map((option) => (
          <option key={option.key} value={option.value}>
            {option.text}
          </option>
        ))}
      </select>
    );
  };

  return (
    <main className="p-4 md:p-8 lg:p-12 mt-16 max-w-7xl mx-auto" id="gap-analysis">
      <h1 className="text-3xl font-bold text-gray-900 mb-6 border-b pb-2">Map Analysis</h1>
      <LoadingAndErrorIndicator loading={loadingGA || loadingStandards} error={error} />

      <div className="bg-white border border-gray-200 rounded-lg shadow-md overflow-hidden">
        <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-gray-200 border-b border-gray-200">
          <div className="p-4 flex flex-col md:flex-row items-start md:items-center space-y-2 md:space-y-0 md:space-x-4">
            <span className="font-semibold text-gray-700 w-20 flex-shrink-0">Base:</span>
            <StandardDropdown
              placeholder="Base Standard"
              options={standardOptions}
              onChange={setBaseStandard}
              value={BaseStandard}
              disabled={loadingStandards}
            />
          </div>
          <div className="p-4 flex flex-col md:flex-row items-start md:items-center space-y-2 md:space-y-0 md:space-x-4 relative">
            <span className="font-semibold text-gray-700 w-20 flex-shrink-0">Compare:</span>
            <StandardDropdown
              placeholder="Compare Standard"
              options={standardOptions}
              onChange={setCompareStandard}
              value={CompareStandard}
              disabled={loadingStandards}
            />
            {gapAnalysis && (
              <div className="md:absolute right-4 top-4 mt-2 md:mt-0">
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(
                      `${window.location.origin}/map_analysis?base=${encodeURIComponent(
                        BaseStandard || ''
                      )}&compare=${encodeURIComponent(CompareStandard || '')}`
                    );
                  }}
                  className="inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition duration-150"
                  title="Copy link to this analysis"
                >
                  <Share2 className="w-4 h-4 mr-2" /> Copy link
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="divide-y divide-gray-200">
          {gapAnalysis &&
            Object.keys(gapAnalysis)
              .sort((a, b) =>
                getDocumentDisplayName(gapAnalysis[a].start, true).localeCompare(
                  getDocumentDisplayName(gapAnalysis[b].start, true)
                )
              )
              .map((key) => (
                <div key={key} className="grid grid-cols-1 md:grid-cols-3">
                  <div className="p-4 md:col-span-1 border-r border-gray-200 bg-gray-50">
                    <a
                      href={getInternalUrl(gapAnalysis[key].start)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:text-blue-800 transition duration-150"
                    >
                      <p className="font-bold hover:underline">
                        {getDocumentDisplayName(gapAnalysis[key].start, true)}
                      </p>
                    </a>
                  </div>
                  <div className="p-4 md:col-span-2">
                    {Object.values<any>(gapAnalysis[key].paths)
                      .sort((a, b) => a.score - b.score)
                      .map((path) => GetResultLine(path, gapAnalysis, key))}

                    {gapAnalysis[key].weakLinks &&
                      Object.values<any>(gapAnalysis[key].weakLinks)
                        .sort((a, b) => a.score - b.score)
                        .map((path) => GetResultLine(path, gapAnalysis, key))}

                    {gapAnalysis[key].extra > 0 && !gapAnalysis[key].weakLinks && (
                      <button
                        onClick={async () => await getWeakLinks(key)}
                        className="mt-3 px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition duration-150"
                      >
                        Show average and weak links ({gapAnalysis[key].extra})
                      </button>
                    )}
                    {Object.keys(gapAnalysis[key].paths).length === 0 && gapAnalysis[key].extra === 0 && (
                      <i className="text-gray-500">No links Found</i>
                    )}
                  </div>
                </div>
              ))}
        </div>
      </div>
    </main>
  );
};