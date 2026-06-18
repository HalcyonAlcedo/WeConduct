/** WeConduct — Simplified Chinese locale (primary) */

export default {
  app: {
    title: 'WeConduct',
  },

  commandBar: {
    menu: {
      file: '文件',
      edit: '编辑',
      view: '视图',
      compile: '编译',
      help: '帮助',
    },
    toolbar: {
      compile: '编译',
      compiling: '编译中…',
      connected: '已连接',
      disconnected: '离线',
      notConnected: '未连接',
      noProject: '未加载项目',
      themeLight: '切换深色主题',
      themeDark: '切换浅色主题',
    },
  },

  input: {
    title: '源输入 (Source Input)',
    ready: '✓ 就绪',
    empty: '空',
    loadExample: '示例',
    clear: '清空',
    sourceKind: '输入类型',
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
    title: '输出 (Output)',
    tabs: {
      summary: '概要',
      diagnostics: '诊断',
      graph: '图模型',
    },
  },

  summary: {
    title: '编译摘要',
    emptyTitle: '编译源代码后在此查看结果',
    emptyDesc: '输入源代码并点击「编译」按钮开始',
    succeeded: '编译成功',
    failed: '编译失败',
    unsupported: '不支持',
    stageBreakdown: '阶段明细',
    stage: '阶段',
    status: '状态',
    diagnosticCount: '诊断数',
    overview: '概览',
    totalStages: '总阶段数',
    succeededStages: '成功',
    failedStages: '失败',
    terminalStage: '终止阶段',
    diagnosticSummary: '诊断汇总',
    graphModel: '图模型',
    noGraph: '未生成图模型',
  },

  diagnostics: {
    title: '诊断目录',
    emptyTitle: '编译源代码后查看诊断信息',
    emptyDesc: '运行编译以生成诊断结果',
    noDiagnostics: '本次编译无诊断信息',
    noDiagnosticsDesc: '编译成功完成，未产生诊断条目',
    allSeverities: '全部严重度',
    severity: {
      fatal: '致命',
      error: '错误',
      degraded: '降级',
      warning: '警告',
      info: '信息',
    },
    stage: '阶段',
    category: '分类',
    message: '信息',
    count: '计数',
    search: '搜索诊断…',
    summary: '{groups} 组诊断 ({total} 条)',
  },

  graph: {
    title: '图模型',
    emptyTitle: '编译后在此查看图模型',
    emptyDesc: '图模型在编译成功后自动生成',
    noGraphTitle: '未生成图模型',
    noGraphDesc: '编译未产生图模型产物 — 查看诊断标签页了解详情',
    nodeKind: {
      execution: '执行',
      control: '控制',
      observe: '观察',
      bridge: '桥接',
    },
    nodeList: '节点列表',
    nodeId: '节点 ID',
    type: '类型',
    sourceAnchor: '来源锚点',
    expansionRole: '扩展角色',
  },

  statusBar: {
    ready: '✓ 就绪',
    offline: '✕ 离线',
    compiling: '◉ 编译中…',
    succeeded: '✓ 编译成功',
    failed: '✕ 编译失败',
    compileCount: '编译 #{n}',
    neverCompiled: '未编译',
    project: '项目:',
    diagnostics: '诊断:',
  },

  common: {
    status: {
      succeeded: '成功',
      failed: '失败',
      pending: '待定',
    },
    close: '关闭',
    retry: '重试',
  },
}
