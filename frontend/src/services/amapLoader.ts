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
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${key}&plugin=AMap.Marker,AMap.InfoWindow,AMap.Polyline`
    script.async = true
    script.onload = () => resolve(window.AMap)
    script.onerror = () => reject(new Error('高德地图 SDK 加载失败'))
    document.head.appendChild(script)
  })

  return loaderPromise
}