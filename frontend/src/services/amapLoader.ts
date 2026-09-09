/**
 * 动态加载高德地图 JS SDK。
 *
 * 为什么动态加载:不在 index.html 写死 key,
 * 让 Vite 把 VITE_AMAP_WEB_KEY 注入 bundle,避免 key 出现在 HTML 源码里。
 */

declare global {
  interface Window {
    AMap?: any
  }
}

let loaderPromise: Promise<any> | null = null

export function loadAMap(): Promise<any> {
  if (loaderPromise) return loaderPromise

  const key = import.meta.env.VITE_AMAP_WEB_KEY
  if (!key || key === '你的高德Web端Key') {
    return Promise.reject(
      new Error('VITE_AMAP_WEB_KEY 未配置,请在 frontend/.env 中填入')
    )
  }

  loaderPromise = new Promise((resolve, reject) => {
    if (window.AMap) {
      resolve(window.AMap)
      return
    }
    const script = document.createElement('script')
    // 基础 maps 不带任何 plugin,AutoComplete/Geocoder/Marker 等插件按需单独加载,
    // 避免 plugin 名称错误导致整个 SDK 失败。
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${key}`
    script.async = true
    script.onload = () => {
      if (window.AMap) resolve(window.AMap)
      else reject(new Error('高德 SDK 加载后未挂载 window.AMap'))
    }
    script.onerror = () => reject(new Error('高德地图 SDK 加载失败'))
    document.head.appendChild(script)
  })

  return loaderPromise
}

/**
 * 按需加载单个 plugin(AMap.Marker / AMap.Geocoder / AMap.AutoComplete 等)。
 * 返回 Promise,resolve 时 plugin 已挂载到 window.AMap 上。
 */
const _pluginPromises = new Map<string, Promise<void>>()

export function loadAMapPlugin(name: string): Promise<void> {
  const cached = _pluginPromises.get(name)
  if (cached) return cached
  const p = loadAMap().then(
    () =>
      new Promise<void>((resolve, reject) => {
        if (!window.AMap) return reject(new Error('AMap 未加载'))
        // 已注册
        if (window.AMap[name]) return resolve()
        window.AMap.plugin(name, () => resolve())
      }),
  )
  _pluginPromises.set(name, p)
  return p
}