import 'leaflet/dist/leaflet.css'
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { useEffect, useMemo } from 'react'
import type { LatLngTuple } from 'leaflet'
import type { LivePosition, Station } from '../types'

type RailwayMapProps = {
  stations: Station[]
  live: LivePosition
}

const demoStationCoordinates: Record<string, [number, number]> = {
  central: [28.6139, 77.2090],
  midtown: [28.6280, 77.2250],
  'north-junction': [28.6460, 77.2410],
}

function MapViewport({ points, live }: { points: LatLngTuple[]; live: LivePosition }) {
  const map = useMap()
  useEffect(() => {
    if (points.length > 1) map.fitBounds(points, { padding: [28, 28], animate: true, duration: 0.6 })
  }, [map, points])
  useEffect(() => {
    map.panTo([live.latitude, live.longitude], { animate: true, duration: 0.45 })
  }, [live.latitude, live.longitude, map])
  return null
}

export default function RailwayMap({ stations, live }: RailwayMapProps) {
  const stationPoints = useMemo<LatLngTuple[]>(() => {
    const known = stations.map((station) => demoStationCoordinates[station.station_id])
    if (known.every(Boolean)) return known as LatLngTuple[]
    const center = [live.latitude, live.longitude] as const
    return stations.map((_, index) => [center[0] + (index - (stations.length - 1) / 2) * 0.012, center[1] + (index - (stations.length - 1) / 2) * 0.015])
  }, [live.latitude, live.longitude, stations])
  const routePoints = [...stationPoints, [live.latitude, live.longitude] as LatLngTuple]

  return <div className="railway-map" aria-label="Interactive railway route map">
    <MapContainer center={[live.latitude, live.longitude]} zoom={12} scrollWheelZoom className="leaflet-map">
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <Polyline positions={stationPoints} pathOptions={{ color: '#087f9f', weight: 5, opacity: 0.9 }} />
      <Polyline positions={stationPoints} pathOptions={{ color: '#8de1de', weight: 2, dashArray: '7 10', opacity: 0.9 }} />
      {stations.map((station, index) => <CircleMarker key={station.station_id} center={stationPoints[index]} radius={index === 0 || index === stations.length - 1 ? 9 : 7} pathOptions={{ color: index === 0 ? '#168b69' : index === stations.length - 1 ? '#bd5360' : '#c07a1d', fillColor: index === 0 ? '#5fd0a8' : index === stations.length - 1 ? '#f18491' : '#f3c36e', fillOpacity: 1, weight: 3 }}><Tooltip direction="top" offset={[0, -8]} permanent>{station.code}</Tooltip></CircleMarker>)}
      <CircleMarker center={[live.latitude, live.longitude]} radius={11} pathOptions={{ color: '#ffffff', fillColor: '#087f9f', fillOpacity: 1, weight: 4, className: 'selected-train-marker' }}><Tooltip direction="top" offset={[0, -10]} permanent>{live.data_source === 'DEMO' ? 'DEMO TRAIN' : 'LIVE TRAIN'}</Tooltip></CircleMarker>
      <MapViewport points={routePoints} live={live} />
    </MapContainer>
    <div className="map-legend"><span><i className="legend-train" />Selected train</span><span><i className="legend-station" />Station</span><span><i className="legend-route" />Route</span><b>{live.data_source === 'DEMO' ? 'DEMO COORDINATES · NOT LIVE GPS' : 'AUTHORIZED LIVE POSITION'}</b></div>
  </div>
}
