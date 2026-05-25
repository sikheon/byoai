package kr.ac.kunsan.byoai.discovery

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import kr.ac.kunsan.byoai.model.DiscoveredSpace

/**
 * 공간 자동발견 = discover.py 의 Kotlin 판. '_byoai._tcp' 서비스를 NsdManager 로
 * browse → resolve → 콜백. (= "기기가 알아서 추가되는" UX)
 */
class SpaceDiscovery(context: Context) {

    private val nsd = context.getSystemService(Context.NSD_SERVICE) as NsdManager
    private var discoveryListener: NsdManager.DiscoveryListener? = null

    fun start(onFound: (DiscoveredSpace) -> Unit, onLost: (String) -> Unit) {
        val listener = object : NsdManager.DiscoveryListener {
            override fun onServiceFound(service: NsdServiceInfo) {
                nsd.resolveService(service, resolveListener(onFound))
            }
            override fun onServiceLost(service: NsdServiceInfo) = onLost(service.serviceName)
            override fun onDiscoveryStarted(t: String) {}
            override fun onDiscoveryStopped(t: String) {}
            override fun onStartDiscoveryFailed(t: String, e: Int) {}
            override fun onStopDiscoveryFailed(t: String, e: Int) {}
        }
        discoveryListener = listener
        nsd.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, listener)
    }

    fun stop() {
        discoveryListener?.let { runCatching { nsd.stopServiceDiscovery(it) } }
        discoveryListener = null
    }

    private fun resolveListener(onFound: (DiscoveredSpace) -> Unit) =
        object : NsdManager.ResolveListener {
            override fun onResolveFailed(s: NsdServiceInfo, e: Int) {}
            override fun onServiceResolved(s: NsdServiceInfo) {
                fun txt(k: String) = s.attributes[k]?.toString(Charsets.UTF_8) ?: ""
                onFound(
                    DiscoveredSpace(
                        serviceName = s.serviceName,
                        host = s.host.hostAddress ?: return,
                        port = s.port,
                        place = txt("place").ifEmpty { s.serviceName },
                        caps = txt("caps"),
                    )
                )
            }
        }

    companion object {
        const val SERVICE_TYPE = "_byoai._tcp."
    }
}
