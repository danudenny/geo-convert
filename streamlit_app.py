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

def detect_geometry_columns(df):
    """Detect potential geometry columns in the DataFrame."""
    geometry_candidates = []

    # Check for common geometry column names
    for col in df.columns:
        if col.lower() in ['geometry', 'geom', 'shape', 'the_geom', 'wkt', 'geojson', 'polygon', 'polygon_corrected', 'polygon_original']:
            geometry_candidates.append(col)

    # Check for columns that might contain GeoJSON or WKT strings
    for col in df.columns:
        if col not in geometry_candidates:
            # Sample a few non-null values
            sample = df[col].dropna().head(5)

            # Check if might be WKT
            if sample.dtype == object and len(sample) > 0:
                try:
                    # Try to parse first element as WKT
                    first_val = sample.iloc[0]
                    if isinstance(first_val, str) and (
                        first_val.startswith('POINT') or
                        first_val.startswith('POLYGON') or
                        first_val.startswith('MULTIPOLYGON') or
                        first_val.startswith('LINESTRING') or
                        first_val.startswith('MULTILINESTRING')
                    ):
                        wkt.loads(first_val)  # Try parsing
                        geometry_candidates.append(col)
                        continue
                except Exception:
                    pass

                # Check if might be GeoJSON
                try:
                    first_val = sample.iloc[0]
                    if isinstance(first_val, str) and '{' in first_val and '}' in first_val:
                        geojson = json.loads(first_val)
                        if 'type' in geojson and 'coordinates' in geojson:
                            geometry_candidates.append(col)
                            continue
                except Exception:
                    pass

def validate_crs(crs_input):
    """Validate CRS input using pyproj"""
    try:
        crs = CRS.from_user_input(crs_input)
        return crs.to_epsg() if crs.to_epsg() else crs.to_string()
    except Exception as e:
        st.error(f"Invalid CRS: {str(e)}")
        return None

def convert_csv_to_geodataframe(df, mode, **kwargs):
    """Convert a pandas DataFrame to a GeoDataFrame."""
    crs = kwargs.get('crs', "EPSG:4326")

    if mode == 'points':
        lon_col = kwargs.get('lon_col')
        lat_col = kwargs.get('lat_col')

        valid_coords = df[lon_col].notna() & df[lat_col].notna()
        if not valid_coords.all():
            st.warning(f"Found {(~valid_coords).sum()} rows with missing coordinates. These will be excluded.")
            df = df[valid_coords].copy()

        geometry = [Point(xy) for xy in zip(df[lon_col], df[lat_col])]
        gdf = gpd.GeoDataFrame(df, geometry=geometry, crs=crs)

    elif mode == 'wkt':
        geom_col = kwargs.get('geom_col')

        valid_geoms = df[geom_col].notna()
        if not valid_geoms.all():
            st.warning(f"Found {(~valid_geoms).sum()} rows with missing geometries. These will be excluded.")
            df = df[valid_geoms].copy()

        try:
            geometry = df[geom_col].apply(wkt.loads)
            df_copy = df.drop(columns=[geom_col])
            gdf = gpd.GeoDataFrame(df_copy, geometry=geometry, crs=crs)
        except Exception as e:
            st.error(f"Error parsing WKT geometries: {str(e)}")
            raise

    elif mode == 'geojson':
        geom_col = kwargs.get('geom_col')

        valid_geoms = df[geom_col].notna()
        if not valid_geoms.all():
            st.warning(f"Found {(~valid_geoms).sum()} rows with missing geometries. These will be excluded.")
            df = df[valid_geoms].copy()

        try:
            geometry = df[geom_col].apply(lambda x: shape(json.loads(x)))
            df_copy = df.drop(columns=[geom_col])
            gdf = gpd.GeoDataFrame(df_copy, geometry=geometry, crs=crs)
        except Exception as e:
            st.error(f"Error parsing GeoJSON geometries: {str(e)}")
            raise

    return gdf

# UI Components
st.title("Geospatial Data Format Converter")
st.write("Convert between CSV, GeoJSON, Parquet, Shapefile, and GeoPackage formats")

# File uploader with size check
uploaded_file = st.file_uploader("Upload your file", 
                                type=["csv", "geojson", "parquet", "gpkg", "zip"],
                                on_change=reset_session_state)

if uploaded_file:
    # Check file size
    if uploaded_file.size > 250 * 1024 * 1024:  # 100MB
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
