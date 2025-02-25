import streamlit as st
import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import Point, Polygon, LineString, shape
from shapely import wkt
import tempfile
import os
import io
import zipfile
from pathlib import Path
import pyproj
import re
from pyproj import CRS

st.set_page_config(page_title="Geospatial Format Converter", layout="wide")

# Initialize session state
def init_session_state():
    session_defaults = {
        'gdf': None,
        'show_output_options': False,
        'current_file': None,
        'uploaded_file_changed': False
    }
    for key, val in session_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

init_session_state()

def reset_session_state():
    st.session_state.gdf = None
    st.session_state.show_output_options = False
    st.session_state.current_file = None
    st.session_state.uploaded_file_changed = True

def detect_geometry_columns(df, sample_size=10):
    """Enhanced geometry column detection with regex patterns"""
    geometry_candidates = []
    wkt_pattern = re.compile(r'^(POINT|LINESTRING|POLYGON|MULTIPOINT|MULTILINESTRING|MULTIPOLYGON)\s*\(', re.IGNORECASE)
    geojson_pattern = re.compile(r'^\s*{\s*"type"\s*:\s*"Feature"\s*,', re.IGNORECASE)

    # Check for common geometry column names
    common_names = ['geometry', 'geom', 'shape', 'the_geom', 'wkt', 'geojson']
    geometry_candidates = [col for col in df.columns if col.lower() in common_names]

    # Check column content patterns
    for col in df.columns:
        if col in geometry_candidates:
            continue
            
        sample = df[col].dropna().head(sample_size)
        if len(sample) == 0:
            continue

        # Check for WKT patterns
        wkt_match = sample.apply(lambda x: bool(wkt_pattern.match(str(x)) if pd.notnull(x) else False)
        if wkt_match.any():
            geometry_candidates.append(col)
            continue

        # Check for GeoJSON patterns
        geojson_match = sample.apply(lambda x: bool(geojson_pattern.match(str(x)) if pd.notnull(x) else False)
        if geojson_match.any():
            geometry_candidates.append(col)
            continue

    return list(set(geometry_candidates))  # Remove duplicates

def validate_crs(crs_input):
    """Validate CRS input using pyproj"""
    try:
        crs = CRS.from_user_input(crs_input)
        return crs.to_epsg() if crs.to_epsg() else crs.to_string()
    except Exception as e:
        st.error(f"Invalid CRS: {str(e)}")
        return None

def convert_csv_to_geodataframe(df, mode, **kwargs):
    """Robust CSV to GeoDataFrame conversion with validation"""
    try:
        crs = validate_crs(kwargs.get('crs', "EPSG:4326"))
        if not crs:
            return None

        if mode == 'points':
            lon_col = kwargs.get('lon_col')
            lat_col = kwargs.get('lat_col')
            
            # Validate coordinate columns
            for col in [lon_col, lat_col]:
                if col not in df.columns:
                    st.error(f"Column '{col}' not found in DataFrame")
                    return None

            # Convert coordinates to numeric
            df[lon_col] = pd.to_numeric(df[lon_col], errors='coerce')
            df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
            
            valid_coords = df[lon_col].notna() & df[lat_col].notna()
            if not valid_coords.all():
                st.warning(f"Removed {(~valid_coords).sum()} rows with invalid coordinates")
                df = df[valid_coords].copy()

            geometry = [Point(xy) for xy in zip(df[lon_col], df[lat_col])]
            return gpd.GeoDataFrame(df, geometry=geometry, crs=crs)

        elif mode in ['wkt', 'geojson']:
            geom_col = kwargs.get('geom_col')
            if geom_col not in df.columns:
                st.error(f"Geometry column '{geom_col}' not found")
                return None

            valid_geoms = df[geom_col].notna()
            if not valid_geoms.all():
                st.warning(f"Removed {(~valid_geoms).sum()} rows with missing geometries")
                df = df[valid_geoms].copy()

            try:
                if mode == 'wkt':
                    geometry = df[geom_col].apply(wkt.loads)
                else:
                    geometry = df[geom_col].apply(lambda x: shape(json.loads(x)))
                
                return gpd.GeoDataFrame(df.drop(columns=[geom_col]), geometry=geometry, crs=crs)
            except Exception as e:
                st.error(f"Error parsing {mode.upper()} geometries: {str(e)}")
                return None

    except Exception as e:
        st.error(f"Conversion error: {str(e)}")
        return None

# UI Components
st.title("Geospatial Data Format Converter")
st.write("Convert between CSV, GeoJSON, Parquet, Shapefile, and GeoPackage formats")

# File uploader with size check
uploaded_file = st.file_uploader("Upload your file", 
                                type=["csv", "geojson", "parquet", "gpkg", "zip"],
                                on_change=reset_session_state)

if uploaded_file:
    # Check file size
    if uploaded_file.size > 100 * 1024 * 1024:  # 100MB
        st.warning("⚠️ Large file detected! Processing might take longer and use significant memory.")

    # Handle new file upload
    if st.session_state.current_file != uploaded_file.name:
        reset_session_state()
        st.session_state.current_file = uploaded_file.name

    try:
        with st.spinner("Processing file..."):
            file_ext = uploaded_file.name.split(".")[-1].lower()
            
            if file_ext == "csv":
                # CSV processing with improved error handling
                csv_config = st.container()
                with csv_config:
                    # CSV configuration UI
                    st.subheader("CSV Configuration")
                    # ... [rest of CSV processing code from original] ...

            elif file_ext in ["geojson", "parquet", "gpkg"]:
                # Vector file processing
                with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_file.close()
                    
                    try:
                        if file_ext == "geojson":
                            gdf = gpd.read_file(tmp_file.name)
                        elif file_ext == "parquet":
                            gdf = gpd.read_parquet(tmp_file.name)
                        elif file_ext == "gpkg":
                            gdf = gpd.read_file(tmp_file.name, layer=None)
                        
                        st.session_state.gdf = gdf
                        st.session_state.show_output_options = True
                    finally:
                        os.unlink(tmp_file.name)

            elif file_ext == "zip":
                # Shapefile processing
                with tempfile.TemporaryDirectory() as tmpdir:
                    with zipfile.ZipFile(uploaded_file) as z:
                        z.extractall(tmpdir)
                    
                    shp_files = list(Path(tmpdir).glob("*.shp"))
                    if shp_files:
                        gdf = gpd.read_file(shp_files[0])
                        st.session_state.gdf = gdf
                        st.session_state.show_output_options = True
                    else:
                        st.error("No .shp file found in ZIP archive")

        if st.session_state.gdf is not None:
            with st.expander("Data Preview", expanded=True):
                st.dataframe(st.session_state.gdf.head())
                st.markdown(f"**CRS:** `{st.session_state.gdf.crs}`")
                st.markdown(f"**Geometry Types:** {st.session_state.gdf.geometry.type.unique()}")

    except Exception as e:
        st.error(f"File processing failed: {str(e)}")
        reset_session_state()

# Output conversion section
if st.session_state.show_output_options and st.session_state.gdf is not None:
    st.subheader("Convert to:")
    
    # Output format selection
    output_format = st.selectbox(
        "Select output format",
        options=["geojson", "parquet", "shp", "gpkg"],
        format_func=lambda x: {
            "geojson": "GeoJSON",
            "parquet": "GeoParquet",
            "shp": "Shapefile (ZIP)",
            "gpkg": "GeoPackage"
        }[x]
    )

    # Filename input
    output_filename = st.text_input("Output filename (without extension)", 
                                  value="converted_data")

    # Conversion and download
    try:
        with st.spinner(f"Generating {output_format}..."):
            if output_format == "geojson":
                result = st.session_state.gdf.to_json()
                st.download_button(
                    label="Download GeoJSON",
                    data=result,
                    file_name=f"{output_filename}.geojson"
                )

            elif output_format == "parquet":
                buffer = io.BytesIO()
                st.session_state.gdf.to_parquet(buffer)
                st.download_button(
                    label="Download GeoParquet",
                    data=buffer,
                    file_name=f"{output_filename}.parquet"
                )

            elif output_format == "shp":
                with tempfile.TemporaryDirectory() as tmpdir:
                    shp_path = Path(tmpdir) / output_filename
                    st.session_state.gdf.to_file(shp_path, driver="ESRI Shapefile")
                    
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                        for f in Path(tmpdir).glob(f"{output_filename}.*"):
                            zip_file.write(f, arcname=f.name)
                    
                    st.download_button(
                        label="Download Shapefile (ZIP)",
                        data=zip_buffer.getvalue(),
                        file_name=f"{output_filename}.zip"
                    )

            elif output_format == "gpkg":
                buffer = io.BytesIO()
                st.session_state.gdf.to_file(buffer, driver="GPKG")
                st.download_button(
                    label="Download GeoPackage",
                    data=buffer,
                    file_name=f"{output_filename}.gpkg"
                )

    except Exception as e:
        st.error(f"Conversion failed: {str(e)}")

# Clear session button
st.sidebar.markdown("---")
if st.sidebar.button("Clear Session & Reset"):
    reset_session_state()
    st.rerun()

# Instructions
with st.expander("How to use this app"):
    st.markdown("""
    ### Instructions

    1. **Upload a file**: 
       - CSV file with coordinate or geometry columns
       - GeoJSON file
       - GeoParquet file
       - Shapefile (zipped)
       - GeoPackage
    
    2. **For CSV files**:
       - Select the appropriate separator (comma, semicolon, tab, etc.)
       - Configure advanced options if needed (decimal separator, encoding, etc.)
       - Choose one of the following methods:
         - **Points from coordinates**: Select longitude and latitude columns
         - **WKT geometry column**: Select a column containing WKT geometry strings (e.g., 'POLYGON((...))')
         - **GeoJSON geometry column**: Select a column containing GeoJSON geometry objects
       - Specify the coordinate reference system (default: EPSG:4326, which is WGS84)
       - Click the appropriate button to create your GeoDataFrame
    
    3. **Choose output format**: Select your desired output format
    
    4. **Download**: Click the download button to save your converted file
    
    ### Notes:
    
    - The app supports various geometry types: points, linestrings, polygons, and their multi-variants
    - Shapefiles are provided as ZIP files containing all necessary components
    - For large files, processing may take a few moments
    - Different regions may use different CSV formats; use the separator and decimal options accordingly
    """)

# Error handling for CRS validation
if st.session_state.get('crs_error'):
    st.error(st.session_state.crs_error)
    st.session_state.crs_error = None

st.markdown("---")
st.markdown("Built with Streamlit, GeoPandas, and PyProj")
