import React, { useEffect, useState, useMemo } from 'react';
import { MapContainer, TileLayer, GeoJSON } from 'react-leaflet';
import { fetchMapData } from '../api';
import axios from 'axios';
import 'leaflet/dist/leaflet.css';

const KERALA_GEOJSON_URL = "https://raw.githubusercontent.com/geohacker/kerala/master/geojsons/district.geojson";

const Map = ({ diseaseName, selectedDate }) => {
    const [geoJsonData, setGeoJsonData] = useState(null);
    const [districtData, setDistrictData] = useState({});

    useEffect(() => {
        axios.get(KERALA_GEOJSON_URL).then(res => {
            setGeoJsonData(res.data);
        }).catch(err => console.error("Error loading map data", err));
    }, []);

    useEffect(() => {
        if (diseaseName) {
            fetchMapData(diseaseName, selectedDate)
                .then(res => {
                    const data = {};
                    res.data.forEach(item => {
                        data[item.district] = item.confirmed_case_count;
                    });
                    setDistrictData(data);
                })
                .catch(err => console.error("Error loading disease data", err));
        }
    }, [diseaseName, selectedDate]);

    const getColor = (count) => {
        return count > 50 ? '#800026' :
            count > 20 ? '#BD0026' :
                count > 10 ? '#E31A1C' :
                    count > 5 ? '#FC4E2A' :
                        count > 2 ? '#FD8D3C' :
                            count > 0 ? '#FEB24C' :
                                '#FFEDA0';
    };

    const style = (feature) => {
        const distName = feature.properties.DISTRICT || feature.properties.District || feature.properties.name;
        const count = districtData[distName] || 0;

        return {
            fillColor: getColor(count),
            weight: 2,
            opacity: 1,
            color: 'white',
            dashArray: '3',
            fillOpacity: 0.7
        };
    };

    const onEachFeature = (feature, layer) => {
        const distName = feature.properties.DISTRICT || feature.properties.District || feature.properties.name;
        const count = districtData[distName] || 0;
        layer.bindTooltip(`<strong>${distName}</strong><br/>Cases: ${count}`);
    };

    // Force GeoJSON re-render when districtData changes by using a key
    const geoJsonKey = useMemo(() => JSON.stringify(districtData), [districtData]);

    if (!geoJsonData) return <div className="p-4 text-center text-gray-500">Loading Map Data...</div>;

    return (
        <div className="h-[500px] w-full rounded-xl overflow-hidden shadow-lg border border-border/50 z-0">
            <MapContainer center={[10.5, 76.2]} zoom={7} scrollWheelZoom={false} style={{ height: '100%', width: '100%' }}>
                <TileLayer
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                    attribution='&copy; OpenStreetMap contributors'
                />
                <GeoJSON key={geoJsonKey} data={geoJsonData} style={style} onEachFeature={onEachFeature} />
            </MapContainer>
        </div>
    );
};

export default Map;
