"""Build the standalone Cycles SDK against an unpacked Gaffer dependency bundle."""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile


VERSION = "5.3.0"
SOURCE_URL = f"https://github.com/blender/cycles/archive/refs/tags/v{VERSION}.zip"
SOURCE_SHA256 = "12f329f0a8061dd119f0f5896492812c600c886a24ebfc39b587e633d5f93828"


def cmakePackages( dependencies, work ) :

	# Release bundles omit many upstream CMake configs. Some Windows exports
	# also reference stripped executables and absolute paths on the CI machine.
	packages = work / "cmake-packages"
	packages.mkdir()
	prefix = dependencies.as_posix()
	options = []
	windows = sys.platform == "win32"
	suffix = { "win32" : ".lib", "darwin" : ".dylib" }.get( sys.platform, ".so" )
	libPrefix = "" if windows else "lib"
	libDir = dependencies / "lib"
	oiioUtil = libDir / f"{libPrefix}OpenImageIO_Util{suffix}"
	for package, libraries in {
		"OpenImageIO" : [ "OpenImageIO", "OpenImageIO_Util" ],
		"OpenEXR" : [ "OpenEXR", "OpenEXRCore", "Iex", "IlmThread" ],
		"OpenColorIO" : [ "OpenColorIO" ],
		"openpgl" : [ "openpgl" ],
		"OSL" : [ "oslcomp", "oslexec", "oslquery", "oslnoise" ],
	}.items() :
		lines = [ "include_guard( GLOBAL )" ]
		for library in libraries :
			target = f"{package}::{library}"
			path = libDir / f"{libPrefix}{library}{suffix}"
			if not path.is_file() :
				# OpenEXR and Imath may include their ABI version in the library name.
				matches = sorted( libDir.glob( f"{libPrefix}{library}-[0-9]*{suffix}" ) )
				if len( matches ) != 1 :
					raise FileNotFoundError( f"Cannot identify {library} in {libDir}" )
				path = matches[0]
			lines += [
				f"add_library({target} UNKNOWN IMPORTED GLOBAL)",
				f'set_target_properties({target} PROPERTIES IMPORTED_LOCATION "{path.as_posix()}" INTERFACE_INCLUDE_DIRECTORIES "{prefix}/include")',
			]
		if package == "OpenImageIO" :
			lines.append( "target_link_libraries(OpenImageIO::OpenImageIO INTERFACE OpenImageIO::OpenImageIO_Util)" )
		if package == "OSL" :
			oslc = "oslc.exe" if windows else "oslc"
			lines += [
				"add_executable(OSL::oslc IMPORTED GLOBAL)",
				f'set_target_properties(OSL::oslc PROPERTIES IMPORTED_LOCATION "{prefix}/bin/{oslc}")',
				f'set(OSL_SHADER_DIR "{prefix}/shaders")',
			]
		( packages / f"{package}Config.cmake" ).write_text( "\n".join( lines ) + "\n", encoding = "utf-8" )
		options.append( f"-D{package}_DIR={packages.as_posix()}" )

	if ( dependencies / "include/OpenImageIO/detail/pugixml/pugixml.hpp" ).is_file() :
		options += [
			f"-DPUGIXML_INCLUDE_DIR={prefix}/include/OpenImageIO/detail/pugixml",
			f"-DPUGIXML_LIBRARY={oiioUtil.as_posix()}",
		]
	return options


def build( dependencies, archive, jobs, gpuBinaries ) :

	dependencies = dependencies.resolve()
	with tempfile.TemporaryDirectory( dir = dependencies.parent ) as temporary :
		work = Path( temporary )
		if archive is None :
			archive = work / "cycles.zip"
			urllib.request.urlretrieve( SOURCE_URL, archive )
		if hashlib.sha256( archive.read_bytes() ).hexdigest() != SOURCE_SHA256 :
			raise RuntimeError( f"Unexpected SHA-256 for Cycles {VERSION} source archive {archive}" )
		with zipfile.ZipFile( archive ) as sourceZip :
			sourceZip.extractall( work )

		source = work / f"cycles-{VERSION}"
		binary = work / "build"
		stage = work / "sdk"
		environment = os.environ.copy()
		environment["PATH"] = os.pathsep.join( [ str( dependencies / "bin" ), str( dependencies / "lib" ), environment["PATH"] ] )
		for variable in ( "LD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH" ) :
			environment[variable] = str( dependencies / "lib" ) + os.pathsep + environment.get( variable, "" )

		# Use the same ABI and device configuration as the Gaffer dependency recipe.
		configure = [
			"cmake", "-S", str( source ), "-B", str( binary ),
			f"-DCMAKE_PREFIX_PATH={dependencies.as_posix()}", f"-DCMAKE_INSTALL_PREFIX={stage.as_posix()}",
			"-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
			"-DWITH_LIBS_PRECOMPILED=OFF", "-DWITH_CYCLES_OPENIMAGEDENOISE=OFF",
			"-DWITH_CYCLES_PATH_GUIDING=ON", "-DWITH_CYCLES_DEVICE_HIP=OFF",
			"-DWITH_CYCLES_HYDRA_RENDER_DELEGATE=OFF", "-DWITH_CYCLES_USD=OFF",
		]
		if sys.platform != "darwin" :
			configure += [
				"-DWITH_CYCLES_DEVICE_CUDA=ON", "-DWITH_CYCLES_DEVICE_OPTIX=ON",
				f"-DWITH_CYCLES_CUDA_BINARIES={'ON' if gpuBinaries else 'OFF'}",
				"-DCYCLES_CUDA_BINARIES_ARCH=sm_60;sm_61;sm_70;sm_75;sm_86;sm_89;sm_120;compute_75",
			]
		configure += cmakePackages( dependencies, work )
		if sys.platform == "win32" :
			configure.append( "-DCMAKE_CONFIGURATION_TYPES=Release" )
			# oneTBB's MSVC headers request tbb12.lib through a linker pragma.
			environment["LIB"] = str( dependencies / "lib" ) + os.pathsep + environment.get( "LIB", "" )
		subprocess.run( configure, check = True, env = environment )
		subprocess.run(
			[ "cmake", "--build", str( binary ), "--config", "Release", "--parallel", str( jobs ), "--target", "install" ],
			check = True, env = environment,
		)

		# Standalone Cycles installs runtime resources, but consumers must also
		# install its headers and static libraries.
		for header in ( source / "src" ).rglob( "*.h" ) :
			target = stage / "include" / header.relative_to( source / "src" )
			target.parent.mkdir( parents = True, exist_ok = True )
			shutil.copy2( header, target )
		shutil.copytree( source / "third_party" / "atomic", stage / "include", dirs_exist_ok = True )
		libDir = binary / "lib"
		if ( libDir / "Release" ).is_dir() :
			libDir /= "Release"
		shutil.copytree( libDir, stage / "lib", dirs_exist_ok = True )
		executable = "cycles.exe" if sys.platform == "win32" else "cycles"
		( stage / "bin" ).mkdir( exist_ok = True )
		( stage / executable ).rename( stage / "bin" / executable )

		# Keep the old SDK intact until the replacement has finished building.
		target = dependencies / "cycles"
		backup = work / "previous-sdk"
		if target.exists() :
			target.rename( backup )
		try :
			stage.rename( target )
		except OSError :
			if backup.exists() :
				backup.rename( target )
			raise


if __name__ == "__main__" :
	parser = argparse.ArgumentParser( description = __doc__ )
	parser.add_argument( "--dependenciesDir", type = Path, required = True, help = "Unpacked Gaffer dependencies." )
	parser.add_argument( "--archive", type = Path, help = "Local copy of the tagged Cycles source ZIP." )
	parser.add_argument( "--jobs", type = int, default = 4 )
	parser.add_argument( "--no-gpu-binaries", action = "store_true", help = "Skip precompiled NVIDIA kernels for local development." )
	args = parser.parse_args()
	if not args.dependenciesDir.is_dir() or args.jobs < 1 :
		parser.error( "Supply an existing dependencies directory and a positive job count." )
	build( args.dependenciesDir, args.archive, args.jobs, not args.no_gpu_binaries )
