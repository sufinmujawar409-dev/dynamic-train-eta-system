import {
  MapContainer,
  Marker,
  Popup,
  Polyline,
  TileLayer,
  CircleMarker,
  Tooltip,
  useMap,
} from "react-leaflet";

import {
  useEffect,
  useMemo,
} from "react";

import L from "leaflet";

import "leaflet/dist/leaflet.css";


// ============================================================
// TYPES
// ============================================================

export interface RailwayStation {
  station_id?: string;
  name: string;
  code: string;
  sequence?: number;

  latitude?: number | null;
  longitude?: number | null;

  data_source?: "DEMO" | "LIVE";
}

export interface RailwayTrain {
  train_id: string;

  train_number?: string;
  number?: string;

  name?: string;

  latitude?: number | null;
  longitude?: number | null;

  speed?: number;
  speed_kmph?: number;

  current_delay?: number;
  delay?: number;

  next_station?: string | null;

  data_source?: "DEMO" | "LIVE";
  data_quality?: "SIMULATED"
    | "LIVE"
    | "STALE"
    | "UNAVAILABLE";

  is_live?: boolean;

  last_updated?: string | null;

  eta?: string | null;
}


export interface RailwayMapProps {
  train: RailwayTrain | null;

  route: RailwayStation[];

  height?: string;

  className?: string;
}


// ============================================================
// LEAFLET ICON
// ============================================================

delete (
  (
    L.Icon.Default.prototype as unknown as {
      _getIconUrl?: unknown;
    }
  )._getIconUrl
);

L.Icon.Default.mergeOptions({
  iconRetinaUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",

  iconUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",

  shadowUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});


// ============================================================
// COORDINATE VALIDATION
// ============================================================

function isValidCoordinate(
  latitude: unknown,
  longitude: unknown,
): boolean {
  return (
    typeof latitude === "number" &&
    typeof longitude === "number" &&
    Number.isFinite(latitude) &&
    Number.isFinite(longitude) &&
    latitude >= -90 &&
    latitude <= 90 &&
    longitude >= -180 &&
    longitude <= 180 &&
    !(latitude === 0 && longitude === 0)
  );
}


// ============================================================
// TRAIN ICON
// ============================================================

function createTrainIcon(): L.DivIcon {
  return L.divIcon({
    className: "dynamic-train-marker",

    html: `
      <div
        style="
          width:44px;
          height:44px;
          border-radius:50%;
          background:linear-gradient(
            135deg,
            #16a34a,
            #22c55e
          );
          border:3px solid white;
          box-shadow:
            0 4px 16px rgba(0,0,0,0.30);
          display:flex;
          align-items:center;
          justify-content:center;
          font-size:22px;
        "
      >
        🚆
      </div>
    `,

    iconSize: [44, 44],

    iconAnchor: [22, 22],

    popupAnchor: [0, -22],
  });
}


// ============================================================
// MAP BOUNDS
// ============================================================

function MapBoundsController({
  coordinates,
}: {
  coordinates: [number, number][];
}) {
  const map = useMap();

  useEffect(() => {
    if (!coordinates.length) {
      return;
    }

    try {
      const bounds =
        L.latLngBounds(coordinates);

      map.fitBounds(
        bounds,
        {
          padding: [35, 35],
          maxZoom: 10,
          animate: true,
        },
      );
    } catch {
      // Ignore fit failures.
    }
  }, [
    map,
    coordinates,
  ]);

  return null;
}


// ============================================================
// MAIN MAP
// ============================================================

export default function RailwayMap({
  train,
  route,
  height = "520px",
  className = "",
}: RailwayMapProps) {

  // ----------------------------------------------------------
  // VALID STATIONS
  // ----------------------------------------------------------

  const validStations =
    useMemo(
      () => {
        return route
          .filter(
            (station) =>
              isValidCoordinate(
                station.latitude,
                station.longitude,
              ),
          )
          .sort(
            (a, b) =>
              (a.sequence ?? 0) -
              (b.sequence ?? 0),
          );
      },
      [route],
    );


  // ----------------------------------------------------------
  // ROUTE LINE
  // ----------------------------------------------------------

  const routeCoordinates =
    useMemo(
      () => {
        return validStations.map(
          (station) =>
            [
              station.latitude!,
              station.longitude!,
            ] as [
              number,
              number,
            ],
        );
      },
      [validStations],
    );


  // ----------------------------------------------------------
  // NEXT STATION
  // ----------------------------------------------------------

  const nextStation =
    useMemo(
      () => {

        if (
          !train?.next_station
        ) {
          return null;
        }

        const query =
          train.next_station
            .trim()
            .toLowerCase();

        return (
          validStations.find(
            (station) => {

              const name =
                station.name
                  .toLowerCase();

              const code =
                station.code
                  .toLowerCase();

              return (
                name === query ||
                code === query ||
                name.includes(query) ||
                query.includes(name)
              );
            },
          ) ?? null
        );

      },
      [
        train?.next_station,
        validStations,
      ],
    );


  // ----------------------------------------------------------
  // TRAIN REPRESENTED POSITION
  // ----------------------------------------------------------

  const representedPosition =
    useMemo(
      () => {

        // Real GPS coordinates.
        if (
          train &&
          isValidCoordinate(
            train.latitude,
            train.longitude,
          )
        ) {
          return [
            train.latitude!,
            train.longitude!,
          ] as [
            number,
            number,
          ];
        }

        // No GPS.
        // Represent train at next station temporarily.
        if (
          nextStation &&
          isValidCoordinate(
            nextStation.latitude,
            nextStation.longitude,
          )
        ) {
          return [
            nextStation.latitude!,
            nextStation.longitude!,
          ] as [
            number,
            number,
          ];
        }

        return null;

      },
      [
        train,
        nextStation,
      ],
    );


  // ----------------------------------------------------------
  // MAP CENTER
  // ----------------------------------------------------------

  const center =
    routeCoordinates.length > 0
      ? routeCoordinates[0]
      : [
          22.9734,
          78.6569,
        ] as [
          number,
          number,
        ];


  // ----------------------------------------------------------
  // FIT COORDINATES
  // ----------------------------------------------------------

  const fitCoordinates =
    useMemo(
      () => {

        const values =
          [
            ...routeCoordinates,
          ];

        if (
          representedPosition
        ) {
          values.push(
            representedPosition,
          );
        }

        return values;

      },
      [
        routeCoordinates,
        representedPosition,
      ],
    );


  const trainNumber =
    train?.train_number ??
    train?.number ??
    train?.train_id ??
    "Train";


  const speed =
    train?.speed_kmph ??
    train?.speed ??
    0;


  const delay =
    train?.current_delay ??
    train?.delay ??
    0;


  // ==========================================================
  // NO COORDINATES
  // ==========================================================

  if (!validStations.length) {

    return (
      <div
        className={className}
        style={{
          height,
          width: "100%",
          borderRadius: "18px",
          overflow: "hidden",
          background:
            "linear-gradient("
            + "135deg,#0f172a,"
            + "#1e293b"
            + ")",
          color: "white",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "30px",
          boxSizing: "border-box",
          textAlign: "center",
        }}
      >

        <div
          style={{
            fontSize: "44px",
            marginBottom: "12px",
          }}
        >
          🗺️
        </div>

        <div
          style={{
            fontSize: "20px",
            fontWeight: 800,
            marginBottom: "8px",
          }}
        >
          Railway map coordinates unavailable
        </div>

        <div
          style={{
            maxWidth: "520px",
            fontSize: "14px",
            lineHeight: 1.6,
            color: "#cbd5e1",
          }}
        >
          NTES live data is connected successfully.
          Add station coordinates in
          <strong>
            {" "}
            station_coordinates.json
          </strong>
          {" "}
          to display the railway route.
        </div>

      </div>
    );
  }


  // ==========================================================
  // MAP
  // ==========================================================

  return (
    <div
      className={className}
      style={{
        height,
        width: "100%",
        borderRadius: "18px",
        overflow: "hidden",
        position: "relative",
      }}
    >

      <MapContainer
        center={center}
        zoom={6}
        scrollWheelZoom={true}
        style={{
          width: "100%",
          height: "100%",
        }}
      >

        <TileLayer
          attribution="© OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />


        <MapBoundsController
          coordinates={fitCoordinates}
        />


        {/* ====================================================
            ROUTE
        ==================================================== */}

        {routeCoordinates.length >= 2 && (
          <>
            <Polyline
              positions={
                routeCoordinates
              }
              pathOptions={{
                color: "#0f172a",
                weight: 8,
                opacity: 0.18,
              }}
            />

            <Polyline
              positions={
                routeCoordinates
              }
              pathOptions={{
                color: "#2563eb",
                weight: 4,
                opacity: 0.90,
              }}
            />
          </>
        )}


        {/* ====================================================
            STATIONS
        ==================================================== */}

        {validStations.map(
          (station) => {

            const isNext =
              nextStation?.code ===
              station.code;

            return (
              <CircleMarker
                key={
                  station.station_id ??
                  station.code
                }
                center={[
                  station.latitude!,
                  station.longitude!,
                ]}
                radius={
                  isNext
                    ? 9
                    : 5
                }
                pathOptions={{
                  color:
                    isNext
                      ? "#f97316"
                      : "#1d4ed8",

                  fillColor:
                    isNext
                      ? "#fb923c"
                      : "#60a5fa",

                  fillOpacity: 1,

                  weight: 2,
                }}
              >

                <Tooltip
                  direction="top"
                  offset={[
                    0,
                    -8,
                  ]}
                >

                  <div
                    style={{
                      fontWeight: 800,
                    }}
                  >
                    {station.name}
                  </div>

                  <div
                    style={{
                      fontSize: "12px",
                    }}
                  >
                    {station.code}
                  </div>

                </Tooltip>

              </CircleMarker>
            );
          },
        )}


        {/* ====================================================
            TRAIN
        ==================================================== */}

        {representedPosition && (
          <Marker
            position={
              representedPosition
            }
            icon={
              createTrainIcon()
            }
          >

            <Popup>

              <div
                style={{
                  minWidth: "210px",
                }}
              >

                <div
                  style={{
                    fontWeight: 800,
                    fontSize: "17px",
                    marginBottom: "6px",
                  }}
                >
                  🚆 {trainNumber}
                </div>

                <div
                  style={{
                    fontWeight: 600,
                    marginBottom: "8px",
                  }}
                >
                  {train?.name ??
                    "Live Train"}
                </div>

                <div
                  style={{
                    fontSize: "13px",
                    lineHeight: 1.7,
                  }}
                >

                  <div>
                    <strong>Status:</strong>{" "}
                    {train?.data_quality ??
                      "LIVE"}
                  </div>

                  <div>
                    <strong>Speed:</strong>{" "}
                    {speed.toFixed(1)}
                    {" "}km/h
                  </div>

                  <div>
                    <strong>Delay:</strong>{" "}
                    {delay}
                    {" "}min
                  </div>

                  <div>
                    <strong>Next:</strong>{" "}
                    {train?.next_station ??
                      "Unavailable"}
                  </div>

                </div>

              </div>

            </Popup>

          </Marker>
        )}

      </MapContainer>


      {/* ========================================================
          TOP STATUS
      ======================================================== */}

      <div
        style={{
          position: "absolute",
          left: "14px",
          top: "14px",
          zIndex: 1000,
          background:
            "rgba(15,23,42,0.92)",
          color: "white",
          padding:
            "12px 15px",
          borderRadius: "12px",
          boxShadow:
            "0 8px 24px rgba(0,0,0,0.24)",
          minWidth: "190px",
        }}
      >

        <div
          style={{
            fontWeight: 800,
            fontSize: "15px",
          }}
        >
          🚆 {trainNumber}
        </div>

        <div
          style={{
            color: "#cbd5e1",
            fontSize: "12px",
            marginTop: "3px",
          }}
        >
          {train?.name ??
            "Dynamic Train ETA"}
        </div>

        <div
          style={{
            marginTop: "7px",
            fontSize: "12px",
          }}
        >
          <span
            style={{
              color: "#22c55e",
            }}
          >
            ●
          </span>
          {" "}
          {train?.is_live
            ? "LIVE NTES"
            : "STALE"}
        </div>

      </div>


      {/* ========================================================
          LEGEND
      ======================================================== */}

      <div
        style={{
          position: "absolute",
          right: "14px",
          bottom: "14px",
          zIndex: 1000,
          background:
            "rgba(255,255,255,0.95)",
          padding: "10px 13px",
          borderRadius: "11px",
          boxShadow:
            "0 5px 18px rgba(0,0,0,0.15)",
          fontSize: "12px",
          lineHeight: 1.7,
        }}
      >

        <div>
          🔵 Station
        </div>

        <div>
          🟠 Next station
        </div>

        <div>
          🚆 Train
        </div>

        <div>
          🔵 Route
        </div>

      </div>

    </div>
  );
}