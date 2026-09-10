from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from backend.app.db.database import Base
from backend.app.db.models import ETAPrediction, Station, Train, TrainPosition, TrainRoute
from backend.app.db.telemetry_repository import TelemetryRepository
from backend.app.schemas import RealtimeTrainEvent, Station as ApiStation, WeatherData


def test_database_models_create_tables_and_relationships() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    table_names = set(inspect(engine).get_table_names())
    assert table_names == {
        "alerts",
        "eta_predictions",
        "stations",
        "train_positions",
        "train_routes",
        "trains",
    }

    Session = sessionmaker(bind=engine)
    with Session.begin() as session:
        train = Train(
            train_number="DEMO-001",
            train_name="DEMO Train",
            source_station="Central",
            destination_station="North",
            status="DEMO",
        )
        station = Station(
            station_code="CEN",
            station_name="Central",
            latitude=28.6,
            longitude=77.2,
        )
        train.routes.append(TrainRoute(station=station, sequence_number=1))
        session.add(train)

    with Session() as session:
        persisted_train = session.query(Train).filter_by(train_number="DEMO-001").one()
        assert persisted_train.routes[0].station.station_code == "CEN"


def test_telemetry_repository_persists_position_and_eta_metadata() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session.begin() as session:
        train = Train(
            train_number="DEMO-101",
            train_name="DEMO Express",
            source_station="Central",
            destination_station="North",
            status="DEMO",
        )
        station = Station(
            station_code="MID",
            station_name="Midtown",
            latitude=28.62,
            longitude=77.22,
        )
        session.add_all([train, station])

    timestamp = datetime.now(timezone.utc)
    event = RealtimeTrainEvent(
        train_id="demo-express-101",
        train_number="DEMO-101",
        latitude=28.61,
        longitude=77.21,
        speed=70,
        current_delay=2,
        next_station="Midtown",
        eta=timestamp,
        timestamp=timestamp,
        data_source="DEMO",
        data_quality="SIMULATED",
        source="DEMO",
        last_updated=timestamp,
        weather=WeatherData.unavailable(),
    )
    assert TelemetryRepository(Session).persist_event(
        event,
        [ApiStation(station_id="midtown", name="Midtown", code="MID", sequence=2)],
    ) is True

    with Session() as session:
        position = session.query(TrainPosition).one()
        prediction = session.query(ETAPrediction).one()
        assert position.data_source == prediction.data_source == "DEMO"
        assert position.data_quality == prediction.data_quality == "SIMULATED"
