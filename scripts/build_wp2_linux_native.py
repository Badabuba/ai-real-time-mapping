"""Build pinned pySLAM CPU native modules inside the documented Linux container.

Does not install system/Python packages. Source stays at the pinned upstream
revision; only its supplied GTSAM patch is applied to the separate GTSAM clone.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=Path('/opt/pyslam'))
parser.add_argument('--logs', type=Path, default=Path('/opt/wp2-build-logs'))
parser.add_argument('--jobs', type=int, default=2)
parser.add_argument('--component', choices=('all','core','g2o','cpp','features','gtsam'), default='all')
parser.add_argument('--configure-only', action='store_true', help='Check GTSAM configuration before compiling it')
args = parser.parse_args()
if args.jobs < 1:
    parser.error('jobs must be positive')
source = args.source.resolve()
logs = args.logs.resolve()
revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
if revision != '96019cfafcfc099ac9866884d7143a9ed1451a0d':
    raise ValueError('unexpected pySLAM source revision')
logs.mkdir(parents=True, exist_ok=True)
def run(name, argv, cwd=None):
    print(name, flush=True)
    with (logs/(name+'.log')).open('w') as stream:
        done = subprocess.run(argv,cwd=cwd or source,stdout=stream,stderr=subprocess.STDOUT)
    if done.returncode:
        print((logs/(name+'.log')).read_text(errors='replace')[-9000:],flush=True)
        raise SystemExit(done.returncode)

base = ['-G','Ninja','-DCMAKE_BUILD_TYPE=Release','-DPYTHON_EXECUTABLE='+sys.executable,
        '-DPython_EXECUTABLE='+sys.executable,'-DPython3_EXECUTABLE='+sys.executable,
        '-DWITH_PYTHON_INTERP_CHECK=ON','-DWITH_MARCH_NATIVE=OFF','-DBUILD_WITH_MARCH_NATIVE=OFF',
        '-Dpybind11_DIR='+subprocess.check_output([sys.executable,'-m','pybind11','--cmakedir'],text=True).strip()]
def build(name,relative,targets=(),options=(),build_dir='build-yulian-linux'):
    if shutil.disk_usage(source).free < 5*1024**3: raise RuntimeError('low workspace disk space')
    path=source/relative; directory=path/build_dir
    run(name+'-configure',['cmake','-S',str(path),'-B',str(directory),*base,*options])
    if args.configure_only:
        return
    command=['cmake','--build',str(directory),'--parallel',str(args.jobs)]
    if targets: command+=['--target',*targets]
    run(name+'-build',command)

selected=args.component
if selected in ('all','core','g2o'):
    build('g2o','thirdparty/g2opy',('g2o',),['-DG2O_BUILD_APPS=OFF','-DG2O_BUILD_EXAMPLES=OFF'])
if selected in ('all','core','cpp'):
    # Debian Qhull 8.0 headers use constructor syntax removed in C++20.
    # Only the optional bounding-box translation units need C++17; retain
    # upstream C++20 for solvers/core and keep all source files unchanged.
    compatibility = logs/'native-compatibility.cmake'
    compatibility.write_text('if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")\n'
        '  set_source_files_properties("${PROJECT_SOURCE_DIR}/volumetric/bounding_boxes_3d.cpp" '
        '"${PROJECT_SOURCE_DIR}/volumetric/bounding_boxes_2d.cpp" '
        'PROPERTIES COMPILE_OPTIONS "-std=c++17")\n'
        '  set_source_files_properties("${PROJECT_SOURCE_DIR}/volumetric/volumetric_module.cpp" '
        'PROPERTIES COMPILE_OPTIONS "-O0;-fno-lto")\n'
        '  if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")\n'
        '    set_property(SOURCE "${PROJECT_SOURCE_DIR}/volumetric/volumetric_module.cpp" '
        'APPEND PROPERTY COMPILE_OPTIONS "-Wno-error=c++11-narrowing")\n'
        '  endif()\n'
        '  if(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")\n'
        '    set_source_files_properties("${PROJECT_SOURCE_DIR}/hamming/hamming_module.cpp" '
        'PROPERTIES COMPILE_OPTIONS "-msse4.1")\n'
        '  endif()\nendif()\n'
        'function(wp2_link_qhull_cpp)\n'
        '  if(TARGET Qhull::qhullcpp)\n'
        '    target_link_libraries(volumetric PRIVATE Qhull::qhullcpp)\n'
        '  endif()\nendfunction()\n'
        'cmake_language(DEFER CALL wp2_link_qhull_cpp)\n')
    build('cpp','cpp',('pyslam_utils','sim3solver','pnpsolver','glutils','trajectory_tools','color_utils','hamming'),
          options=['-DCMAKE_PROJECT_pyslam_utils_INCLUDE='+str(compatibility)])
    if shutil.which('clang++') is None:
        raise RuntimeError('Clang is required for the large volumetric binding; see containers/wp2.Dockerfile')
    build('volumetric','cpp',('volumetric',),options=[
        '-DCMAKE_PROJECT_pyslam_utils_INCLUDE='+str(compatibility),
        '-DCMAKE_C_COMPILER=clang','-DCMAKE_CXX_COMPILER=clang++',
        '-DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF'],build_dir='build-yulian-clang')
if selected in ('all','core','features'):
    build('orb','thirdparty/orbslam2_features',('orbslam2_features',))
    prefix=source/'thirdparty/pydbow3/modules/dbow3/install'
    build('dbow3','thirdparty/pydbow3/modules/dbow3',('install',),['-DCMAKE_INSTALL_PREFIX='+str(prefix)])
    build('pydbow3','thirdparty/pydbow3',('pydbow3',))
    build('dbow2','thirdparty/pydbow2/modules/dbow2')
    build('pydbow2','thirdparty/pydbow2',('pydbow2',))
    build('obindex2','thirdparty/pyibow/modules/obindex2/lib',build_dir='build')
    build('ibow-lcd','thirdparty/pyibow/modules/ibow-lcd',build_dir='build')
    build('pyibow','thirdparty/pyibow',('pyibow','pyobindex2'))
if selected in ('all','gtsam'):
    path=source/'thirdparty/gtsam_local'
    if not path.exists():
        run('gtsam-clone',['git','clone','--depth','1','--branch','4.2a9','https://github.com/borglab/gtsam.git',str(path)])
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip()
    assert revision=='c57988fe554e7213c77fe379c1d7c483de26ad33',revision
    patch=source/'thirdparty/gtsam.patch'
    if subprocess.run(['git','apply','--check',str(patch)],cwd=path,capture_output=True).returncode==0:
        run('gtsam-patch',['git','apply',str(patch)],cwd=path)
    else:
        subprocess.run(['git','apply','--reverse','--check',str(patch)],cwd=path,check=True)
    build('gtsam','thirdparty/gtsam_local',('gtsam_py','CppUnitLite'),[
        '-DCMAKE_INSTALL_PREFIX='+str(path/'install'),'-DGTSAM_USE_SYSTEM_EIGEN=ON','-DGTSAM_BUILD_WITH_MARCH_NATIVE=OFF',
        '-DGTSAM_WITH_TBB=OFF','-DGTSAM_BUILD_PYTHON=ON','-DGTSAM_BUILD_TESTS=OFF',
        '-DGTSAM_BUILD_EXAMPLES_ALWAYS=OFF','-DGTSAM_BUILD_UNSTABLE=OFF',
        '-DGTSAM_THROW_CHEIRALITY_EXCEPTION=OFF','-DGTSAM_PYTHON_VERSION=3.11'])
    if not args.configure_only:
        run('gtsam-install',['cmake','--install',str(path/'build-yulian-linux')])
        run('gtsam-python-install',[sys.executable,'-m','pip','install','--no-build-isolation','--no-deps',str(path/'build-yulian-linux/python')])
        build('gtsam-factors','thirdparty/gtsam_factors',('gtsam_factors',))
print('WP2_NATIVE_CONFIGURATION_READY' if args.configure_only else 'WP2_NATIVE_BUILD_READY',flush=True)
