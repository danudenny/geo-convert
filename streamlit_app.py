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

st.set_page_config(page_title="Geospatial Format Converter", layout="wide")

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
    
    return geometry_candidates

def convert_csv_to_geodataframe(df, mode, **kwargs):
    """
    Convert a pandas DataFrame to a GeoDataFrame based on the specified mode.
    
    Modes:
    - 'points': Create Point geometries from longitude and latitude columns
    - 'wkt': Parse geometries from a WKT column
    - 'geojson': Parse geometries from a GeoJSON column
    """
    crs = kwargs.get('crs', "EPSG:4326")
    
    if mode == 'points':
        lon_col = kwargs.get('lon_col')
        lat_col = kwargs.get('lat_col')
        
        # Filter out rows with invalid coordinates
        valid_coords = df[lon_col].notna() & df[lat_col].notna()
        if not valid_coords.all():
            st.warning(f"Found {(~valid_coords).sum()} rows with missing coordinates. These will be excluded.")
            df = df[valid_coords].copy()
        
        # Create geometry column
        geometry = [Point(xy) for xy in zip(df[lon_col], df[lat_col])]
        gdf = gpd.GeoDataFrame(df, geometry=geometry, crs=crs)
        
    elif mode == 'wkt':
        geom_col = kwargs.get('geom_col')
        
        # Filter out rows with missing geometry
        valid_geoms = df[geom_col].notna()
        if not valid_geoms.all():
            st.warning(f"Found {(~valid_geoms).sum()} rows with missing geometries. These will be excluded.")
            df = df[valid_geoms].copy()
        
        # Convert WKT strings to Shapely geometries
        try:
            geometry = df[geom_col].apply(wkt.loads)
            df_copy = df.drop(columns=[geom_col])
            gdf = gpd.GeoDataFrame(df_copy, geometry=geometry, crs=crs)
        except Exception as e:
            st.error(f"Error parsing WKT geometries: {str(e)}")
            raise
            
    elif mode == 'geojson':
        geom_col = kwargs.get('geom_col')
        
        # Filter out rows with missing geometry
        valid_geoms = df[geom_col].notna()
        if not valid_geoms.all():
            st.warning(f"Found {(~valid_geoms).sum()} rows with missing geometries. These will be excluded.")
            df = df[valid_geoms].copy()
        
        # Convert GeoJSON strings to Shapely geometries
        try:
            geometry = df[geom_col].apply(lambda x: shape(json.loads(x)))
            df_copy = df.drop(columns=[geom_col])
            gdf = gpd.GeoDataFrame(df_copy, geometry=geometry, crs=crs)
        except Exception as e:
            st.error(f"Error parsing GeoJSON geometries: {str(e)}")
            raise
            
    return gdf

def save_file_to_zip(gdf, file_format, filename="converted_data"):
    """Save a GeoDataFrame to a specified format and compress it into a ZIP file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)
        
        if file_format == "shp":
            # Shapefile creates multiple files, so save to temp directory
            shapefile_path = temp_path / filename
            gdf.to_file(shapefile_path, driver="ESRI Shapefile")
            
            # Create zip file containing all shapefile components
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED) as zip_file:
                for file_path in temp_path.glob(f"{filename}.*"):
                    zip_file.write(file_path, arcname=file_path.name)
            
            zip_buffer.seek(0)
            return zip_buffer.getvalue()
        
        elif file_format == "gpkg":
            gpkg_path = temp_path / f"{filename}.gpkg"
            gdf.to_file(gpkg_path, driver="GPKG")
            
            with open(gpkg_path, "rb") as f:
                return f.read()

def extract_geometry_info(gdf):
    """Extract information about the geometries in the GeoDataFrame."""
    if gdf is None or len(gdf) == 0:
        return "No geometries found"
        
    geometry_types = gdf.geometry.type.value_counts().to_dict()
    crs = gdf.crs
    bounds = gdf.total_bounds
    
    info = f"**Geometry Types**: {', '.join([f'{k} ({v})' for k, v in geometry_types.items()])}\n"
    info += f"**CRS**: {crs}\n"
    info += f"**Bounds** (minx, miny, maxx, maxy): {bounds[0]:.4f}, {bounds[1]:.4f}, {bounds[2]:.4f}, {bounds[3]:.4f}"
    
    return info

st.title("Geospatial Data Format Converter")
st.write("Convert between CSV, GeoJSON, Parquet, Shapefile, and GeoPackage formats")

# Initialize session state variables if they don't exist
if 'gdf' not in st.session_state:
    st.session_state.gdf = None
if 'show_output_options' not in st.session_state:
    st.session_state.show_output_options = False

# File uploader
uploaded_file = st.file_uploader("Upload your file", type=["csv", "geojson", "parquet", "gpkg", "zip"], key="file_uploader")

if uploaded_file is not None:
    # Determine file type from extension
    file_extension = uploaded_file.name.split(".")[-1].lower()
    
    try:
        # Process the file based on its type
        if file_extension == "csv":
            # CSV separator selector
            separator_options = {
                ",": "Comma (,)",
                ";": "Semicolon (;)",
                "\t": "Tab (\\t)",
                "|": "Pipe (|)",
                " ": "Space ( )"
            }
            
            selected_sep = st.selectbox(
                "Select CSV separator",
                options=list(separator_options.keys()),
                format_func=lambda x: separator_options[x],
                index=0,  # Default to comma
                key="separator_selector"
            )
            
            # Additional CSV reading options
            csv_options = {}
            
            with st.expander("Advanced CSV Options"):
                csv_options["decimal"] = st.selectbox(
                    "Decimal separator",
                    options=[".", ","],
                    index=0  # Default to period
                )
                
                csv_options["encoding"] = st.selectbox(
                    "File encoding",
                    options=["utf-8", "latin1", "iso-8859-1", "cp1252"],
                    index=0  # Default to UTF-8
                )
                
                has_header = st.checkbox("File has header", value=True)
                
                if not has_header:
                    prefix = st.text_input("Column prefix", "col")
                    # Only set header=None and names with prefix when no header
                    csv_options["header"] = None
                    # Generate column names with prefix
                    preview_df = pd.read_csv(uploaded_file, sep=selected_sep, nrows=1)
                    num_cols = len(preview_df.columns)
                    csv_options["names"] = [f"{prefix}{i}" for i in range(num_cols)]
                else:
                    csv_options["header"] = 0
            
            # Try to read the CSV with selected separator
            try:
                df = pd.read_csv(uploaded_file, sep=selected_sep, **csv_options)
                st.write("CSV file preview:")
                st.dataframe(df.head())
                
                # Detect potential geometry columns
                geometry_candidates = detect_geometry_columns(df)
                
                # Get column names for coordinates
                columns = df.columns.tolist()
                
                # Try to detect coordinate columns automatically
                lon_col_guess = next((col for col in columns if col.lower() in ["lon", "longitude", "long", "x"]), columns[0])
                lat_col_guess = next((col for col in columns if col.lower() in ["lat", "latitude", "y"]), columns[1] if len(columns) > 1 else columns[0])
                
                # Choose geometry creation method
                geometry_mode = st.radio(
                    "How to create geometries?",
                    options=["Points from coordinates", "WKT geometry column", "GeoJSON geometry column"],
                    index=0 if not geometry_candidates else 1
                )
                
                if geometry_mode == "Points from coordinates":
                    col1, col2 = st.columns(2)
                    with col1:
                        lon_col = st.selectbox("Longitude column", options=columns, index=columns.index(lon_col_guess))
                    with col2:
                        lat_col = st.selectbox("Latitude column", options=columns, index=columns.index(lat_col_guess))
                        
                    crs = st.text_input("Coordinate Reference System", "EPSG:4326")
                    
                    if st.button("Create GeoDataFrame from Points"):
                        # Create GeoDataFrame using point coordinates
                        gdf = convert_csv_to_geodataframe(df, 'points', lon_col=lon_col, lat_col=lat_col, crs=crs)
                        st.session_state.gdf = gdf
                        st.write("GeoDataFrame created successfully!")
                        st.write("Preview:")
                        st.dataframe(gdf.head())
                        st.write("Geometry Information:")
                        st.markdown(extract_geometry_info(gdf))
                        st.session_state.show_output_options = True
                        
                elif geometry_mode == "WKT geometry column":
                    geom_col_options = geometry_candidates if geometry_candidates else columns
                    geom_col = st.selectbox("WKT geometry column", options=geom_col_options, 
                                        index=0 if geom_col_options else 0)
                    crs = st.text_input("Coordinate Reference System", "EPSG:4326")
                    
                    if st.button("Create GeoDataFrame from WKT"):
                        # Create GeoDataFrame using WKT geometry
                        gdf = convert_csv_to_geodataframe(df, 'wkt', geom_col=geom_col, crs=crs)
                        st.session_state.gdf = gdf
                        st.write("GeoDataFrame created successfully!")
                        st.write("Preview:")
                        st.dataframe(gdf.head())
                        st.write("Geometry Information:")
                        st.markdown(extract_geometry_info(gdf))
                        st.session_state.show_output_options = True
                        
                elif geometry_mode == "GeoJSON geometry column":
                    geom_col_options = geometry_candidates if geometry_candidates else columns
                    geom_col = st.selectbox("GeoJSON geometry column", options=geom_col_options,
                                        index=0 if geom_col_options else 0)
                    crs = st.text_input("Coordinate Reference System", "EPSG:4326")
                    
                    if st.button("Create GeoDataFrame from GeoJSON"):
                        # Create GeoDataFrame using GeoJSON geometry
                        gdf = convert_csv_to_geodataframe(df, 'geojson', geom_col=geom_col, crs=crs)
                        st.session_state.gdf = gdf
                        st.write("GeoDataFrame created successfully!")
                        st.write("Preview:")
                        st.dataframe(gdf.head())
                        st.write("Geometry Information:")
                        st.markdown(extract_geometry_info(gdf))
                        st.session_state.show_output_options = True
                        
            except pd.errors.ParserError as e:
                st.error(f"Error parsing CSV with selected separator '{selected_sep}': {str(e)}")
                st.info("Try a different separator or check if the file is properly formatted.")
            
        elif file_extension in ["geojson", "parquet", "gpkg"]:
            # Determine the appropriate method to read the file
            if file_extension == "geojson":
                gdf = gpd.read_file(uploaded_file)
            elif file_extension == "parquet":
                gdf = gpd.read_parquet(uploaded_file)
            elif file_extension == "gpkg":
                gdf = gpd.read_file(uploaded_file, driver="GPKG")
                
            st.session_state.gdf = gdf
            st.write(f"{file_extension.upper()} data preview:")
            st.dataframe(gdf.head())
            st.write("Geometry Information:")
            st.markdown(extract_geometry_info(gdf))
            st.session_state.show_output_options = True
            
        elif file_extension == "zip":
            # Check if it's likely a zipped shapefile
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
                        zip_ref.extractall(tmpdir)
                    
                    # Look for .shp file
                    shp_files = list(Path(tmpdir).glob("*.shp"))
                    if not shp_files:
                        st.error("No .shp file found in the ZIP archive.")
                    else:
                        gdf = gpd.read_file(shp_files[0])
                        st.session_state.gdf = gdf
                        st.write("Shapefile data preview:")
                        st.dataframe(gdf.head())
                        st.write("Geometry Information:")
                        st.markdown(extract_geometry_info(gdf))
                        st.session_state.show_output_options = True
            except Exception as e:
                st.error(f"Error processing ZIP file: {str(e)}")
        
        # Show output options if we have a GeoDataFrame
        if st.session_state.show_output_options and st.session_state.gdf is not None:
            st.subheader("Convert to:")
            
            # All possible output formats
            all_formats = ["geojson", "parquet", "shp", "gpkg"]
            
            # Remove the input format from options
            if file_extension in ["geojson", "parquet", "shp", "gpkg"]:
                format_options = [fmt for fmt in all_formats if fmt != file_extension]
            else:
                format_options = all_formats
            
            # Output format selection
            output_format = st.selectbox(
                "Select output format",
                options=format_options,
                format_func=lambda x: {
                    "geojson": "GeoJSON",
                    "parquet": "GeoParquet",
                    "shp": "Shapefile (zipped)",
                    "gpkg": "GeoPackage"
                }[x],
                key="output_format_selector"  # Unique key for the widget
            )
            
            # Get the GeoDataFrame from session state
            gdf = st.session_state.gdf
            
            # Generate download data based on selected format
            if output_format == "geojson":
                geojson_data = gdf.to_json()
                st.download_button(
                    label="Download GeoJSON",
                    data=geojson_data,
                    file_name="converted_data.geojson",
                    mime="application/json",
                    key="download_button_geojson"  # Unique key for this download button
                )
            
            elif output_format == "parquet":
                parquet_buffer = io.BytesIO()
                gdf.to_parquet(parquet_buffer)
                parquet_buffer.seek(0)
                st.download_button(
                    label="Download GeoParquet",
                    data=parquet_buffer,
                    file_name="converted_data.parquet",
                    mime="application/octet-stream",
                    key="download_button_parquet"  # Unique key for this download button
                )
            
            elif output_format == "shp":
                shapefile_zip = save_file_to_zip(gdf, "shp")
                st.download_button(
                    label="Download Shapefile (ZIP)",
                    data=shapefile_zip,
                    file_name="converted_data_shapefile.zip",
                    mime="application/zip",
                    key="download_button_shp"  # Unique key for this download button
                )
            
            elif output_format == "gpkg":
                geopackage_data = save_file_to_zip(gdf, "gpkg")
                st.download_button(
                    label="Download GeoPackage",
                    data=geopackage_data,
                    file_name="converted_data.gpkg",
                    mime="application/geopackage+sqlite3",
                    key="download_button_gpkg"  # Unique key for this download button
                )
                
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        import traceback
        st.error(traceback.format_exc())

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

# Footer
st.markdown("---")
st.markdown("Built with Streamlit, GeoPandas, and Pandas")
