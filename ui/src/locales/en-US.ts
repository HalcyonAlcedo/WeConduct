/** WeConduct — English locale (Phase 2 skeleton) */

import type zhCN from './zh-CN'

const enUS: typeof zhCN = {
  app: {
    title: 'WeConduct',
  },

  commandBar: {
    menu: {
      file: 'File',
      edit: 'Edit',
      view: 'View',
      compile: 'Compile',
      help: 'Help',
    },
    toolbar: {
      compile: 'Compile',
      compiling: 'Compiling…',
      connected: 'Connected',
      disconnected: 'Offline',
      notConnected: 'Not connected',
      noProject: 'No project loaded',
      themeLight: 'Switch to dark theme',
      themeDark: 'Switch to light theme',
    },
  },

  input: {
    title: 'Source Input',
    ready: '✓ Ready',
    empty: 'Empty',
    loadExample: 'Example',
    clear: 'Clear',
    sourceKind: 'Source Type',
  },

  pipeline: {
    stages: {
      parse: 'parse',
      bind: 'bind',
      validate: 'validate',
      normalize: 'normalize',
      lower: 'lower',
      emit: 'emit',
    },
  },

  output: {
    title: 'Output',
    tabs: {
      summary: 'Summary',
      diagnostics: 'Diagnostics',
      graph: 'Graph',
    },
  },

  summary: {
    title: 'Compilation Summary',
    emptyTitle: 'Compile source to see results',
    emptyDesc: 'Enter source code and click Compile to begin',
    succeeded: 'Compilation Succeeded',
    failed: 'Compilation Failed',
    unsupported: 'Unsupported',
    stageBreakdown: 'Stage Breakdown',
    stage: 'Stage',
    status: 'Status',
    diagnosticCount: 'Diag Count',
    overview: 'Overview',
    totalStages: 'Total Stages',
    succeededStages: 'Succeeded',
    failedStages: 'Failed',
    terminalStage: 'Terminal Stage',
    diagnosticSummary: 'Diagnostic Summary',
    graphModel: 'Graph Model',
    noGraph: 'No graph model produced',
  },

  diagnostics: {
    title: 'Diagnostic Catalog',
    emptyTitle: 'Compile source to see diagnostics',
    emptyDesc: 'Run compilation to generate diagnostic results',
    noDiagnostics: 'No diagnostics for this compilation',
    noDiagnosticsDesc: 'Compilation completed without any diagnostic entries',
    allSeverities: 'All Severities',
    severity: {
      fatal: 'Fatal',
      error: 'Error',
      degraded: 'Degraded',
      warning: 'Warning',
      info: 'Info',
    },
    stage: 'Stage',
    category: 'Category',
    message: 'Message',
    count: 'Count',
    search: 'Search diagnostics…',
    summary: '{groups} groups ({total} entries)',
  },

  graph: {
    title: 'Graph Model',
    emptyTitle: 'Compile source to see graph',
    emptyDesc: 'Graph model is generated automatically on successful compilation',
    noGraphTitle: 'No Graph Model',
    noGraphDesc: 'Compilation did not produce a graph model — check the Diagnostics tab',
    nodeKind: {
      execution: 'Execution',
      control: 'Control',
      observe: 'Observe',
      bridge: 'Bridge',
    },
    nodeList: 'Node List',
    nodeId: 'Node ID',
    type: 'Type',
    sourceAnchor: 'Source Anchor',
    expansionRole: 'Expansion Role',
  },

  statusBar: {
    ready: '✓ Ready',
    offline: '✕ Offline',
    compiling: '◉ Compiling…',
    succeeded: '✓ Compilation Succeeded',
    failed: '✕ Compilation Failed',
    compileCount: 'Compile #{n}',
    neverCompiled: 'Not compiled',
    project: 'Project:',
    diagnostics: 'Diagnostics:',
  },

  common: {
    status: {
      succeeded: 'Succeeded',
      failed: 'Failed',
      pending: 'Pending',
    },
    close: 'Close',
    retry: 'Retry',
  },
}

export default enUS
